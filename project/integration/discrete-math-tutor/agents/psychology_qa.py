"""实验心理学样章问答：核验依据、生成解释、核对引用。"""
import json
import re
from pydantic import BaseModel, ConfigDict, Field
from agents.context_sufficiency import ContextSufficiency
from llm.client import LLMError
from agents.course_prompts import SCOPE,GATE

GENERATE = SCOPE + '''
用简体中文直接解释问题，控制在约500字以内。重点短语可用**加粗**，最多三处。
教材事实用[1]等证据ID紧邻标注；只引用给定证据，回答中必须有引用。
只输出JSON：{"answer":"带引用的回答"}。不要输出思考过程或声称已经生成图解。'''
AUDIT = SCOPE + '''
你是回答核对器。核对草稿是否回答问题、事实是否受证据支持、引用是否正确。
补充例子不需要逐字见于教材，但不得与教材冲突。不得把缺失内容当作原书结论。
只输出JSON：{"supported":true或false,"reason":"简短核对结论"}，不修改草稿。'''

class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    answer: str = Field(min_length=1, max_length=6000)

class Audit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    supported: bool
    reason: str = Field(min_length=1, max_length=500)

def explain(llm, question, sources):
    evidence = [{'id':str(i), 'text':source['text'], 'section':source['section']}
                for i, source in enumerate(sources, 1)]
    if llm.mock:
        return {'status':'unavailable', 'answer':'当前为离线模式，不能进行真实教材问答核验。', 'citations':[]}
    decision = ContextSufficiency(llm, system=GATE).check(question, evidence, topic='第四章 被试间设计')
    if not decision.allowed:
        return {'status':decision.status, 'answer':decision.reply(), 'citations':[], 'reason':decision.reason,
                'missing':decision.missing}
    payload = {'question':question, 'evidence':evidence}
    def call(system, data):
        return llm.chat_json([{'role':'system','content':system},
                             {'role':'user','content':json.dumps(data,ensure_ascii=False)}],
                             temperature=0, max_tokens=1800, retries=0, timeout=35)
    try:
        answer = Draft.model_validate(call(GENERATE, payload)).answer.strip()
        ids = list(dict.fromkeys(re.findall(r'\[(\d+)\]', answer)))
        if not ids or not set(ids) <= {item['id'] for item in evidence}:
            raise ValueError('回答引用无效')
        audit = Audit.model_validate(call(AUDIT, payload | {'draft':answer}))
        if not audit.supported:
            return {'status':'rejected','answer':'这次回答未通过教材核对，请缩小问题范围或选中具体段落再问。',
                    'citations':[], 'reason':audit.reason}
        return {'status':'completed', 'answer':answer, 'reason':audit.reason,
                'citations':[{'id':id, **sources[int(id)-1]} for id in ids]}
    except (LLMError, ValueError, TypeError):
        return {'status':'unavailable', 'answer':'问答或引用核验暂不可用，请稍后重试。', 'citations':[]}
