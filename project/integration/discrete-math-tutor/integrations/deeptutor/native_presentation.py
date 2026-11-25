"""原生消息的公共投影；呈现规则仍由固定版本 DeepTutor 前端负责。"""
from copy import deepcopy
import re

PRESENTATION_VERSION = "deeptutor-message/v1"
EVENT_TYPES = frozenset(("stage_start", "stage_end", "thinking", "observation", "content",
    "tool_call", "tool_result", "progress", "sources", "result", "error", "done", "wait_for_input"))
TRACE_FIELDS = frozenset("""call_id parent_call_id phase label call_kind trace_role trace_group trace_kind
    trace_id call_state call_role answer_visible reasoning_chars finish_reason requested_max_tokens
    usage_reported prompt_tokens completion_tokens total_tokens reasoning_tokens output_chars content_chars
    tool_call_chars tool_call_count reasoning_budget_exhausted absorbed_into_final step_id round query
    tool_name tool_source tool_provider provider progress_fraction elapsed_s block_id trace_layer
    output_mode quality question_index total_questions research_status_key topic_index topic_title
    report_part section_index section_count section_title subagent_channel subagent_kind subagent_name
    consult_index subagent_merge_id status ask_user_resolved tool tool_call_id parent_id current total
    assistant_content_offset ask_user_tool_call_id reply_preview""".split())
ARG_FIELDS = frozenset("""query queries mode limit source_id source_ids chapter_id section_id asset_id
    title topic description objective_id path_id question_id content text name filename language
    question questions options intro multi_select prompt header allow_free_text explanation path command pattern""".split())
QUESTION_FIELDS = frozenset(("question_id", "question", "question_type", "options", "difficulty"))


def public_text(text):
    text = re.sub(r"(?i)(api[_-]?key|authorization|access[_-]?token|password)([\s:=]+)[^\s,;]+", r"\1\2[redacted]", str(text))
    text = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+',r'\1[redacted]',text)
    text = re.sub(r'(?i)(api[_-]?key["\']?\s*:\s*["\'])[^"\']+',r'\1[redacted]',text)
    text = re.sub(r'(?<![:/\w])/(?:mnt|home|Users|tmp|var)/[^\s"<>]+',lambda match:match[0].rsplit('/',1)[-1],text)
    return re.sub(r"[A-Za-z]:[\\/][^\s\"<>]+", lambda match: match[0].replace("\\", "/").rsplit("/", 1)[-1], text)


def public_value(value):
    if isinstance(value, dict):
        return {key: public_value(item) for key,item in value.items()
                if not key.startswith("_") and not re.search(r"(?i)secret|password|token|api.?key|authorization|system_prompt|correct_answer|answer_key|reference_answer",key)}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    return public_text(value) if isinstance(value, str) else value


def public_args(value):
    if not isinstance(value, dict):
        return {}
    return {key: public_value(item) for key, item in value.items() if key in ARG_FIELDS}


def project_event(event, task, binding):
    """只公开显示协议字段；模型请求、私有工具上下文和原始异常留在 worker。"""
    if binding.get("turn_id") and event.get("turn_id") not in (None,"",binding["turn_id"]):
        raise ValueError("原生事件不属于当前回合")
    kind = event.get("type")
    if kind not in EVENT_TYPES:
        return None
    seq = event.get("seq")
    if type(seq) is not int or seq < 1:
        raise ValueError("原生事件序号无效")
    raw = event.get("metadata") or {}
    if not isinstance(raw, dict):
        raise ValueError("原生事件元数据无效")
    meta = {key: public_value(value) for key, value in raw.items() if key in TRACE_FIELDS
            and isinstance(value, (str, int, float, bool))}
    content = public_text(event.get("content") or "")
    if kind == "error":
        content = "本轮执行未完成，请重试。"
    if kind == "tool_call":
        meta["args"] = public_args(raw.get("args"))
        content = str(raw.get("tool_name") or event.get("content") or event.get("source") or "")
    if kind == "sources":
        content = ""
    if kind == "result":
        # 只有宿主核验并保存后才公开交付物；原生 result 仍保留为流程标记。
        content = ""
    qa = raw.get("qa_pair")
    if isinstance(qa, dict):
        meta["qa_pair"] = {key: deepcopy(value) for key, value in qa.items() if key in QUESTION_FIELDS}
    from .native_delivery import public_mastery_events
    mastery = public_mastery_events([event])
    if mastery:
        meta["tool_metadata"] = mastery[0]["metadata"]["tool_metadata"]
        content = ""
    # 私有题卡正文不公开；一般工具保留经脱敏后的原版可见结果。
    if kind == "tool_result" and not mastery:
        tool = raw.get("tool_metadata") or {}
        if isinstance(tool, dict) and isinstance(tool.get("provider"), str):
            meta["tool_metadata"] = {"provider": tool["provider"]}
    tool = raw.get('tool_metadata') or {}
    if isinstance(tool, dict):
        for name,fields in {
            'course_handoff':('target','prompt','reason','ref_id','label','course_id'),
            'mastery_handoff':('kind','path_id','session_id','label','reason','topic_type'),
        }.items():
            value=tool.get(name)
            if isinstance(value,dict):
                meta.setdefault('tool_metadata',{})[name]={key:public_value(value[key]) for key in fields if key in value}
    if kind=='progress' and isinstance(raw.get('ask_user_draft'),dict):
        meta['ask_user_draft']=public_value(raw['ask_user_draft'])
        if isinstance(raw.get('draft_call_id'),str):meta['draft_call_id']=raw['draft_call_id']
    if isinstance(raw.get("answers"), list):
        meta["answers"] = [{"questionId": str(item.get("questionId") or item.get("id") or ""),
                            "text": public_text(item.get("text") or "")}
                           for item in raw["answers"] if isinstance(item, dict)]
    from .native_executor import _pending
    pending = _pending(event)
    if pending:
        meta.setdefault("tool_metadata", {})["ask_user"] = pending
        if kind == "wait_for_input":
            kind = "tool_result"
        if kind == "tool_result":
            content = ""
    return {"type": kind, "source": str(event.get("source") or ""),
            "stage": str(event.get("stage") or ""), "content": content, "metadata": meta,
            "seq": seq, "turn_id": binding.get("turn_id") or str(event.get("turn_id") or ""),
            "timestamp": event.get("timestamp", 0)}


def identity(task, binding):
    return {"version": PRESENTATION_VERSION, "task_id": task["id"],
            "task_revision": task["revision"], "turn_id": binding.get("turn_id"),
            "capability": binding.get("start", {}).get("capability", "chat")}


def compact_events(events):
    """相邻同轮文字合并，保留原生分段边界，避免把逐 token 事件重复存入宿主历史。"""
    output=[]
    for event in events:
        previous=output[-1] if output else None
        if (previous and event['type'] in ('content','thinking','observation')
                and all(previous.get(key)==event.get(key) for key in ('type','source','stage','metadata'))):
            previous['content']+=event['content']
            previous['seq']=event['seq']
        else:
            output.append(deepcopy(event))
    return output


def checked_presentation(student_id, session_id, task_id, revision):
    from .task_projection import checked_task
    from database.learning_tasks import TaskConflict, LearningTaskRepository
    row=LearningTaskRepository().get(student_id,session_id,task_id)
    binding=row.get('context',{}).get('native_turn') or {}
    # 正式保存会推进一次revision；只允许本次执行自己的结算，不接受澄清后的新执行。
    settled=(row['status'] in ('completed','failed','awaiting_clarification')
             and row['revision']==revision+1 and binding.get('presentation_revision')==revision)
    if row['revision']!=revision and not settled:
        raise TaskConflict('task_conflict','任务版本已变化')
    row=checked_task(student_id,session_id,task_id,row['revision'],allow_active=True)
    if binding.get('presentation_version')!=PRESENTATION_VERSION:
        raise TaskConflict('legacy_presentation','旧对话不恢复过程展示')
    key=binding.get('key') or {}
    if (key.get('student_id')!=student_id or key.get('session_id')!=session_id
            or key.get('task_id')!=task_id):
        raise TaskConflict('task_conflict','原生回合绑定已变化')
    from knowledge.pdf_reader import documents
    versions=row.get('context',{}).get('document_versions') or {}
    current={item['document_id']:item['version'] for item in documents()}
    if any(current.get(doc)!=version for doc,version in versions.items()):
        raise TaskConflict('source_changed','教材版本已变化')
    return row,binding
