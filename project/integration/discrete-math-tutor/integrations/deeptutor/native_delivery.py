"""原生结果到宿主正式交付的映射；不放宽引用或页面动作权限。"""
from copy import deepcopy
from types import SimpleNamespace


def public_quiz(metadata):
    summary = metadata.get('summary') or {}
    if not isinstance(summary, dict):raise ValueError('题目统计无效')
    rows = summary.get('results') or []
    if not isinstance(rows, list):raise ValueError('题目列表无效')
    requested = summary.get('requested')
    if (summary.get('success') is not True or type(requested) is not int or not 1 <= requested <= 50
            or summary.get('completed') != requested or summary.get('failed', 0) != 0
            or len(rows) != requested):
        raise ValueError('题目尚未完整生成')
    questions = []
    for row in rows:
        if not isinstance(row, dict):raise ValueError('题目条目无效')
        qa = row.get('qa_pair') or {}
        if not isinstance(qa, dict):raise ValueError('题目结构无效')
        if not isinstance(qa.get('question'), str) or not qa['question'].strip():
            raise ValueError('题目正文为空')
        public = {key: deepcopy(qa[key]) for key in ('question_id','question','question_type','options','difficulty') if key in qa}
        questions.append({'qa_pair': public})
    return {'response': f'已生成 {requested} 道练习题。', 'mode': metadata.get('mode', 'custom'),
        'summary': {'success': True, 'requested': requested, 'completed': requested, 'failed': 0, 'results': questions}}


def publication_sources(binding, state, versions):
    sources = deepcopy(binding.get('sources') or [])
    indexed = {item['index']: item for item in sources}
    for item in state.get('sources') or []:
        if item.get('type') != 'heart_textbook_evidence':
            continue
        evidence = item.get('location', {}).get('evidence') or {}
        doc, version, index = item.get('document_id'), item.get('version'), item.get('index')
        if (versions.get(doc) != version or evidence.get('document_id') != doc
                or evidence.get('document_version') != version or type(index) is not int or index < 1):
            raise ValueError('原生教材来源版本或编号无效')
        if index in indexed:
            if indexed[index].get('source_id') != item.get('source_id'):
                raise ValueError('同一引用编号对应不同原文')
            continue
        indexed[index] = deepcopy(item)
    return [indexed[index] for index in sorted(indexed)]


def project_reader_actions(rows, task):
    from agents.tools.first_wave_runtime import ReaderGotoTool
    from agents.tools.first_wave import ReadFailure
    versions = task['context'].get('document_versions') or {}
    resources = SimpleNamespace(binding=SimpleNamespace(documents=tuple(versions.items())))
    context = SimpleNamespace(task_id=task['id'], session_id=task['session_id'])
    actions = []
    for row in rows[-1:]:
        args = {key: row[key] for key in ('document_id','version','page','quote') if key in row}
        if versions.get(args.get('document_id')) != args.get('version'):
            raise ValueError('阅读动作不属于本轮教材版本')
        try:
            result, _ = ReaderGotoTool(task['revision']).read(args, context, resources)
        except ReadFailure as exc:
            raise ValueError('阅读动作未通过宿主核验') from exc
        actions.append(result['action'])
    return actions


def public_mastery_events(events):
    """只投影原生公开题卡/判定协议，不把工具正文或私有题目送到页面。"""
    fields = {
        'mastery_question': ('question_id','prompt','question_type','difficulty','attempt','allow_free_text'),
        'mastery_grade': ('question_id','is_correct','learner_answer','correct_label','correct_body','explanation','result','independent'),
        'mastery_skip_question': ('question_id','skipped'),
    }
    output = []
    for event in events:
        if event.get('type') != 'tool_result':
            continue
        metadata = event.get('metadata') or {}
        values = metadata.get('tool_metadata') or metadata
        selected = {}
        for name, allowed in fields.items():
            raw = values.get(name)
            if name == 'mastery_grade' and isinstance(raw, dict):
                raw = raw.get('result')
            if not isinstance(raw, dict) or not raw.get('question_id'):
                continue
            public = {key: deepcopy(raw[key]) for key in allowed if key in raw}
            if name == 'mastery_question':
                public['objective'] = {key: raw.get('objective', {}).get(key, '') for key in ('id','name')}
                public['options'] = [{key: option.get(key, '') for key in ('label','body')}
                                     for option in raw.get('options', []) if isinstance(option, dict)]
            selected[name] = {'result': public} if name == 'mastery_grade' else public
        if selected:
            output.append({'type':'tool_result','metadata':{'tool_metadata':selected}})
    return output
