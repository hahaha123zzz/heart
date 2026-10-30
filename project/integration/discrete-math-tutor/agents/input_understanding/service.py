"""规则先行的单轮理解；缺省关闭，不为简单消息新增模型调用。"""
import os
import re
from models.input_understanding import GroundedTurn, InputEnvelope, TaskFrame, ScopedDirective
from agents.input_understanding.context import state_projection, pending_question
from agents.input_understanding.rules import normalize, resume_requested, explanation_before_resume, non_submission, choice_submission


def mode():
    value = os.getenv('INPUT_UNDERSTANDING_MODE', 'off').strip().lower()
    return value if value in ('off', 'shadow', 'active') else 'off'


def explicit_switch(request):
    for match in re.finditer(r'换个知识点|换个话题|不学这个|改学|(?:我要|我想|开始)学习第.{1,3}章', request.message):
        prefix = request.message[max(0, match.start()-6):match.start()]
        if not re.search(r'(?:不要|不用|别|不想|先不|不必).{0,2}$', prefix):
            return True
    return False


def understand(context, request, *, llm=None, classifier=None):
    normalized, positions = normalize(request.message)
    header, refs = state_projection(context, request)
    kind = ('clarification' if request.task_id else 'selection' if request.selection else
            'exercise' if request.exercise_target else 'object_action' if any((request.visualization_target,
            request.truth_table_target,request.relation_target)) else 'text')
    envelope = InputEnvelope(request_id=request.request_id or 'unassigned', raw_text=request.message,
        normalized_text=normalized or request.message, source_positions=positions or list(range(len(request.message))), input_kind=kind)
    pending = pending_question(context)
    constraints, directives = [], []
    patterns = {'hint_only': r'只(?:给|要)(?:一个|一点)?提示',
                'no_full_answer': r'不要(?:直接)?(?:给我?|我)?完整答案|不要替我作答|只(?:给|要)(?:一个|一点)?提示',
                'no_questions': r'不要(?:再)?(?:出题|问我)|不出题|只讲不考|只讲解不测验',
                'verdict_only': r'只(?:判断|确认)(?:一下)?(?:对错|是否正确)'}
    for key, pattern in patterns.items():
        match = re.search(pattern, request.message)
        if match:
            constraints.append(key)
            directives.append(ScopedDirective(scope='turn',key=key,value=True,quote=match[0]))
    preference = re.search(r'(?:以后|今后)(?:都|请)?(?:讲得|回答)?(?:详细一点|详细点|简短一点|简短点)', request.message)
    if preference:
        directives.append(ScopedDirective(scope='persistent',key='answer_length',
            value=0.0 if '简短' in preference[0] else 1.0,quote=preference[0],requires_confirmation=True))
    direct = re.search(r'(?:这(?:一)?题|本题).{0,4}直接(?:给我?|告诉我)?答案',request.message)
    if direct:
        directives.append(ScopedDirective(scope='question' if pending else 'turn',target_ref='pending' if pending else None,
            key='response_style',value='direct',quote=direct[0]))
    query = explanation_before_resume(request.message)
    def frame(index, action, query=request.message, target=None, dependencies=()):
        return TaskFrame(task_frame_id=f'f{index}', action=action,query=query,
            target_ref=target,depends_on=list(dependencies),constraints=list(constraints))
    from agents.q5_runtime import Q5Runtime
    if request.selected_option in ('q5sp:confirm','q5:confirm'):
        tasks=[frame(1,'confirm_learning_plan')]
    elif Q5Runtime.is_plan_request(request.message):
        tasks=[frame(1,'propose_learning_plan')]
    elif (header.current_activity_id
          and not re.search(r'(?:不要|不用|别|先不).{0,2}(?:回到|返回|恢复|继续)', request.message)
          and re.search(r'(?:回到|返回|恢复|继续)(?:刚才|原来)?的?(?:学习安排|本次安排|学习计划)', request.message)):
        tasks=[frame(1,'resume_learning_activity',target='activity')]
    elif pending and query:
        tasks=[frame(1,'provide_hint' if 'hint_only' in constraints else 'explain_content',query),
               frame(2,'resume_pending_question',query='',target='pending',dependencies=('f1',))]
    elif pending and len([r for r in refs if r.kind == 'figure' and r.origin == 'request']) == 1:
        figure = next(r for r in refs if r.kind == 'figure' and r.origin == 'request')
        tasks=[frame(1,'explain_content',target=figure.ref_id)]
    elif pending and resume_requested(request.message):
        # 只有完整恢复短句才可重放；包含其他要求时留给受限解析或正常回答。
        if re.fullmatch(r'(?:请|现在)?(?:回到|返回)(?:原来|刚才|上面|原)?的?(?:那道|这道|原)?(?:题|检查)(?:，我还没作答)?[。！!\s]*', request.message):
            tasks=[frame(1,'resume_pending_question',target='pending')]
        else:
            tasks=[frame(1,'explain_content')]
    elif pending and not non_submission(request.message):
        options = pending.get('options') or []
        from agents.deeptutor_learning.pending import parse_options
        texts = [f"{o['label']}. {o['body']}" if isinstance(o,dict) and 'label' in o and 'body' in o else str(o) for o in options]
        label = choice_submission(request.message,parse_options(texts)) if texts else ''
        if label:
            tasks=[frame(1,'submit_student_answer',target='pending')]
        elif 'hint_only' in constraints:
            tasks=[frame(1,'provide_hint')]
        elif constraints or re.search(r'(?:请|先)(?:说明|讲解)',request.message):
            tasks=[frame(1,'explain_content')]
        else:
            tasks=[frame(1,'discuss_claim')]
    else:
        action=('provide_hint' if 'hint_only' in constraints or ('no_full_answer' in constraints
                and not re.search(r'解释|说明|讲解|比较|区分|区别',request.message)) else
                'compare_content' if re.search(r'比较|区别|区分',request.message) else
                'request_practice' if re.search(r'考考我|出一道|分步练习',request.message) else
                'discuss_claim' if re.search(r'我觉得.{0,30}(?:没控制好|不合理|有问题)',request.message) else 'explain_content')
        from agents.input_understanding.references import primary_reference
        target = primary_reference(context,request,refs)
        tasks=[frame(1,action,target=target)]
    understood=GroundedTurn(envelope=envelope,context=header,references=refs,tasks=tasks,directives=directives)
    from agents.input_understanding.references import bind_mention
    understood = bind_mention(understood, context, request)
    writes = 0
    for pattern in (r'确认(?:本次)?(?:学习)?(?:计划|安排)', r'提交(?:我的)?答案|我选\s*[A-D]', r'删除(?:这条|当前)?(?:学习路径|学习计划)'):
        matches = list(re.finditer(pattern, request.message))
        if any(not re.search(r'(?:不要|不用|别|先不).{0,2}$',request.message[max(0,m.start()-6):m.start()]) for m in matches):
            writes += 1
    if writes > 1:
        return GroundedTurn.model_validate(understood.model_dump() | {'resolution_status':'partial',
            'unresolved':[*understood.unresolved,'mixed_state_changes']})
    if llm is not None and os.getenv('INPUT_UNDERSTANDING_SEMANTIC_ENABLED','0') == '1':
        from agents.input_understanding.semantic import needs_resolution, resolve
        if needs_resolution(understood) and understood.resolution_status not in ('ambiguous', 'missing'):
            understood=resolve(understood,context,llm)
    # 分类器只能返回受控语义标注；对象、任务与约束不在其可写边界内。
    # 复杂解析已调用模型时不再串行分类；未配置合并协议的维度保持未知。
    if classifier is not None and understood.model_calls == 0:
        from agents.input_understanding.semantic import annotate
        from pydantic import ValidationError
        from llm.client import LLMError
        try:
            understood=annotate(understood,context,classifier)
        except (ValidationError,ValueError,LLMError):
            # 标签不可用不能推翻已验证的规则任务，也不制造学生误区。
            pass
    return understood
