"""检查点仅从宿主任务读取；返回前重验所有权、记忆版本和教材原件。"""
from copy import deepcopy
from agents.composition_execution import source_digest, restored_blocks
from agents.response_composition import ResponseComposer
from models.learning_response import ResponsePlan


def checked_checkpoint(row):
    from integrations.deeptutor.task_projection import checked_task, source_pointers
    current=checked_task(row['student_id'],row['session_id'],row['id'],row['revision'],allow_active=True)
    state=deepcopy(current['context'].get('composition_checkpoint'))
    if not state or state.get('schema')!='response-checkpoint/v1':
        raise ValueError('没有可恢复的内容检查点')
    if source_digest(state['sources'])!=state['source_digest']:
        raise ValueError('检查点来源不一致')
    # 覆盖未使用但后续仍会生成的来源，不能只校验已经展示的引用。
    refs=[{'evidence':source['location']['evidence']} for source in state['sources']]
    source_pointers(state['payload'],{'pdf_references':refs},state['document_versions'])
    releases={r['evidence'].get('textbook_release') for r in refs if r['evidence'].get('textbook_release')}
    if releases:
        from knowledge.course_release import binding
        if releases!={binding()['release_id']}:raise ValueError('检查点教材发布身份已变化')
    composer=ResponseComposer(ResponsePlan.model_validate(state['plan']))
    composer.sources={s['source_id']:s for s in state['sources']}
    composer.accepted=restored_blocks(composer.plan,state['accepted'])
    composer.legacy_label_blocks=set(state.get('legacy_label_blocks',[])) if state.get('label_policy_version') else set(composer.accepted)
    for block in composer.accepted.values():composer._validate(block)
    if state.get('final_result'):
        from database.database import session_scope
        from database.models import ConversationRow
        final=state['final_result']
        with session_scope() as db:
            conversation=db.get(ConversationRow,final.get('conversation_id'))
            if (not conversation or conversation.student_id!=row['student_id'] or conversation.session_id!=row['session_id']
                    or conversation.role!='assistant' or conversation.content!=final.get('reply')):
                raise ValueError('最终对话已删除或不属于当前会话')
    return state,composer


def partial_result(row):
    state,composer=checked_checkpoint(row)
    published=state.get('publication')
    if not published or not composer.accepted:return None
    envelope=composer.publication(sources=state['sources'],references=published['pdf_references'],
        reply=published['reply'],response_id=state['payload'].get('request_id') or row['id'])
    if state.get('final_result'):
        final=state['final_result']
        published={key:final[key] for key in ('reply','pdf_references','textbook_sources','conversation_id') if key in final}
        envelope=final['learning_response']
    return {**published,'learning_response':{**envelope,'status':'partial'},'answer_status':'partial_answer',
        'task_id':row['id'],'task_revision':row['revision'],'step_advanced':False}
