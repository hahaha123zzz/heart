"""内容块有界执行与检查点；在现有AgentLoop取证完成后运行，不执行工具。"""
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
from time import monotonic, time

from agents.response_composition import ResponseComposer
from models.learning_response import ResponsePlan, GeneratedBlock
from llm.answer_events import answer_kwargs, current_answer
from llm.client import LLMError
from llm.execution_budget import check_budget, current_budget

composition_io = ContextVar('composition_io', default=None)


def enabled():
    import os
    return (os.getenv('RESPONSE_BLOCK_STREAMING_ENABLED', '0') == '1'
            and os.getenv('RESPONSE_COMPOSITION_ENABLED','0') == '1')


def source_digest(sources):
    return hashlib.sha256(json.dumps(sources,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def active_spent(state):
    spent=float(state.get('active_seconds',0));limit=float(state.get('active_limit_seconds',120))
    if state.get('in_flight'):
        reserved=float(state.get('in_flight_limit',min(90,max(0,limit-spent))))
        spent+=min(reserved,max(0,time()-state['updated_at']))
    return spent


def resume_allowed(state):
    if state.get('final_result'):return True  # 完整对话已提交，只补任务回执，不再生成。
    return state.get('calls',0)<8 and active_spent(state)<state.get('active_limit_seconds',120)


def restored_blocks(plan, rows):
    blocks={key:GeneratedBlock.model_validate(value) for key,value in rows.items()}
    if not blocks.keys()<={b.block_id for b in plan.blocks} or any(key!=b.block_id for key,b in blocks.items()):
        raise ValueError('composition_checkpoint_block_identity')
    if any(not set(b.depends_on)<=blocks.keys() for b in plan.blocks if b.block_id in blocks):
        raise ValueError('composition_checkpoint_dependency_missing')
    return blocks


def reference_key(reference):
    e=reference.get('evidence') or {}
    if not e.get('document_id') or not e.get('document_version'):
        raise ValueError('composition_reference_identity_required')
    return json.dumps([e.get(k) for k in ('document_id','document_version','source_block_id',
        'block_start','block_end','media_kind')] +
        ([e.get('page'),e.get('evidence_id')] if e.get('source_block_id') is None or e.get('media_kind')=='image' else []))


def freeze_publication(publication, previous=None):
    """只在第一次使用来源时追加编号；后批不能重写已发布的前缀。"""
    import re
    old=(previous or {}).get('pdf_references',[])
    keys={reference_key(ref):i+1 for i,ref in enumerate(old)}
    refs=deepcopy(old);mapping={}
    incoming=publication.get('pdf_references') or []
    seen=set()
    for reference in incoming:
        key=reference_key(reference);seen.add(key)
        if key not in keys:
            keys[key]=len(refs)+1;refs.append(None)
        index=keys[key]
        mapping[reference['source_index']+1]=index
        refs[index-1]={**deepcopy(reference),'source_index':index-1}
    if not incoming or not set(keys) <= seen:
        raise ValueError('composition_published_source_disappeared')
    def marker(match):
        if int(match[1]) not in mapping:
            raise ValueError('composition_unbound_marker')
        return f'[{mapping[int(match[1])]}]'
    reply=re.sub(r'\[(\d+)\]',marker,publication['reply'])
    if previous and not reply.startswith(previous['reply']):
        raise ValueError('composition_published_prefix_changed')
    # 编号变化后同步结论中的markers，保留已核验原文身份。
    from knowledge.grounded_citations import claims_for
    claims=claims_for(reply)
    for ref in refs:
        ref['evidence']['claims']=[c for c in claims if ref['source_index']+1 in c['markers']]
    return {**publication,'reply':reply,'pdf_references':refs}


def execute_batches(loop, request, result, messages, collector, *, composer, gate, max_characters=None):
    """同一依赖前沿合并为一次生成；最多8次调用，累计活动预算不因恢复重置。
    max_characters 仅为兼容旧调用；None 表示不按字符数分配或拒绝。"""
    io=composition_io.get()
    saved=deepcopy(io.get('restored') or {}) if io else {}
    if saved and (saved['plan']!=composer.plan.model_dump() or saved['source_digest']!=source_digest(result.sources)):
        raise ValueError('composition_checkpoint_input_changed')
    composer.accepted=restored_blocks(composer.plan,saved.get('accepted',{}))
    composer.legacy_label_blocks=set(saved.get('legacy_label_blocks',[])) if saved.get('label_policy_version') else set(composer.accepted)
    composer.sources={s['source_id']:s for s in result.sources}
    omitted=set(saved.get('omitted',[]));calls=saved.get('calls',0)
    if type(calls) is not int or not 0<=calls<=8:raise ValueError('composition_checkpoint_call_budget')
    previous=saved.get('publication')
    # 重新运行纯结构/来源校验；checkpoint不是绕过当前门禁的通行证。
    verifier=ResponseComposer(composer.plan)
    verifier.sources={s['source_id']:s for s in result.sources}
    for block in composer.accepted.values():
        verifier._validate(block)
    consumed=active_spent(saved)
    budget=current_budget.get()
    started=budget.started if budget else monotonic()
    if budget:
        budget.deadline-=consumed

    def guard():
        check_budget()
        if request.cancellation:request.cancellation.check()
        if request.guard:request.guard()

    def checkpoint(in_flight=False):
        guard()
        state={'schema':'response-checkpoint/v1','plan':composer.plan.model_dump(),
            'sources':result.sources,'source_digest':source_digest(result.sources),
            'accepted':{key:block.model_dump() for key,block in composer.accepted.items()},
            'label_policy_version':2,'legacy_label_blocks':sorted(composer.legacy_label_blocks),
            'omitted':sorted(omitted),'calls':calls,'publication':previous,
            'active_seconds':consumed+monotonic()-started,'active_limit_seconds':budget.seconds if budget else 120,
            'in_flight_limit':min(90,budget.remaining()) if budget else 90,
            'in_flight':in_flight,'updated_at':time()}
        if io:io['save'](state)

    try:
        while len(composer.accepted)+len(omitted)<len(composer.plan.blocks):
            guard()
            if calls>=8:
                raise LLMError('内容块执行达到本轮调用上限')
            ready=[b for b in composer.plan.blocks if b.block_id not in composer.accepted and b.block_id not in omitted
                   and set(b.depends_on)<=composer.accepted.keys()]
            if not ready:
                raise ValueError('composition_dependency_unavailable')
            batch_plan=composer.plan.model_copy(update={'blocks':[b.model_copy(update={'depends_on':[]}) for b in ready]})
            remaining=[b for b in composer.plan.blocks if b.block_id not in composer.accepted and b.block_id not in omitted]
            allocation=(max(16,(max_characters-len(composer.render())-2)*len(ready)//len(remaining))
                        if max_characters is not None else None)
            batch=ResponseComposer(batch_plan)
            candidate=None
            for repair in range(2):
                guard()
                if calls>=8:raise LLMError('内容块执行达到本轮调用上限')
                calls+=1;checkpoint(in_flight=True)
                prompt=[*messages,{'role':'system','content':batch.instructions(result.sources)+
                    (f'\n当前批次至多{allocation}字（含引用与示例标签），仅完成当前semantic_type。'
                     if allocation is not None else '\n仅完成当前semantic_type。')+
                    '\n完整内容计划只读，未来模块的案例/比较留待后续，不提前完成：'+json.dumps(composer.plan.model_dump(),ensure_ascii=False)+
                    '\n此前已发布正文只读，不能重复或修改：\n'+composer.render()}]
                if candidate:prompt.append({'role':'user','content':candidate})
                collector('progress','生成下一部分讲解',{'blocks':[b.block_id for b in ready]})
                from agents.turn_context import record_request
                record_request(request.context, prompt, [], model=getattr(loop.llm, "model", ""),
                               max_tokens=request.round_max_tokens)
                response=loop.llm.chat_with_tools(prompt,[],temperature=request.temperature,
                    max_tokens=request.round_max_tokens,timeout=90,tool_choice='none',**answer_kwargs('progress'))
                result.rounds+=1
                for key,value in (response.usage or {}).items():result.usage[key]=result.usage.get(key,0)+int(value)
                guard()
                if response.tool_calls or response.finish_reason=='length':raise LLMError('内容块输出未完成或包含工具调用')
                old=composer.accepted
                parsed=False
                try:
                    batch.accept(response.text,result.sources)
                    parsed=True
                    if allocation is not None and len(batch.render())>allocation:raise ValueError(f'当前批次超过{allocation}字，必须压缩当前未发布模块')
                    if any(b.semantic_type=='worked_example' and b not in ready for b in remaining):
                        if any(c.provenance in ('generated_example','analogy') for b in batch.accepted.values() for c in b.claims):
                            raise ValueError('案例由后续worked_example模块负责，本批只讲含义')
                    trial={**composer.accepted,**batch.accepted}
                    composer.accepted=trial
                    complete=all(b.block_id in trial or not b.required for b in composer.plan.blocks)
                    ok,reason=gate(composer.render(),result,complete)
                    if not ok:raise ValueError(reason)
                    published=freeze_publication(result._publication,previous)
                    break
                except ValueError as exc:
                    composer.accepted=old
                    if repair:raise
                    # 本批未发布内容可修订；此前已发布块不能改写或丢弃。
                    if parsed:batch=ResponseComposer(batch_plan)
                    candidate='只修复当前批次，保留已发布部分：'+str(exc)[:1000]
            omitted.update(b.block_id for b in ready if b.block_id not in batch.accepted)
            previous=published;checkpoint()
            answer=current_answer.get()
            if answer:
                envelope=composer.publication(sources=result.sources,references=published['pdf_references'],
                    reply=published['reply'],response_id=request.request_id)
                answer.blocks({**published,'learning_response':{**envelope,'status':'in_progress'},
                    'answer_status':'partial_answer'})
        guard()
        ok,reason=gate(composer.render(),result,True)
        if not ok:raise ValueError(reason)
        result._publication=freeze_publication(result._publication,previous)
        result.final_text=composer.render();result.completed=True
        result.messages=[*messages,{'role':'assistant','content':result.final_text}]
        collector('done','',{'rounds':result.rounds,'tool_steps':result.tool_steps})
        return result
    except (LLMError,ValueError) as exc:
        checkpoint()
        result.error='quality_rejected' if isinstance(exc,ValueError) else 'model_unavailable'
        result.final_text='本次讲解尚未全部完成，可恢复已保存部分后继续。'
        result.messages=messages
        collector('error',result.final_text,{'code':result.error})
        return result
