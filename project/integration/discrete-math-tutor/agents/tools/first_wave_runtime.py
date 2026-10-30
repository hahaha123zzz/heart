"""宿主可信绑定与结构化状态发布；教材事实仍进入原有核验。"""
import json
import re
from agents.tools.first_wave import ReadBinding, ReadResources, readonly_tools, _ReadTool, ReadFailure
from agents.tools.first_wave_services import CourseReadService
from agents.tools.first_wave_contracts import DEFINITIONS, SCOPES, TEXT_LIMIT
from memory.readonly_context import ReadonlyMemoryContext


STRUCTURED_TOOL = {'outline': 'material_outline', 'catalog': 'kb_files',
                   'personal_state': 'read_memory', 'reader_action': 'reader_goto'}


def purpose(message):
    text = re.sub(r'\s+', '', message).replace('讲解偏好', '偏好')
    if re.search(r'解释|讲解|为什么|如何|证明|比较|区别|原理', text):
        return 'textbook'
    if re.search(r'跳转|带我到|打开.*页|定位到', text):
        return 'reader_action'
    if re.search(r'目录|有哪些小节|章节结构', text):
        return 'outline'
    if re.search(r'几[份本个].*(教材|文档|资料)|(?:教材|资料|文档).*(几[份本个]|有哪些|数量)', text):
        return 'catalog'
    if re.search(r'记得我|我的.*(?:偏好|画像|基础)|我喜欢.*(?:讲|学)', text):
        return 'personal_state'
    return 'textbook'


def bind_resources(request, memory):
    from knowledge.course_config import COURSE_ID
    from knowledge.course_release import binding
    from knowledge.pdf_reader import documents
    release = binding()
    bound = ReadBinding(request.student_id, request.session_id, request.task_id or request.request_id,
        COURSE_ID, release['release_id'], tuple((d['document_id'], d['version']) for d in documents()))
    resources = ReadResources(bound, CourseReadService(), ReadonlyMemoryContext(memory) if memory else None)
    if memory is not None and re.search(r'刚才|这个来源|这条来源|(?:这|那)(?:张|幅|个)?图', request.message):
        from database.learning_tasks import LearningTaskRepository
        recent = LearningTaskRepository().recent(request.student_id, request.session_id, limit=1)
        previous = recent[-1]['result'] if recent else {}
        allowed = {r.get('evidence', {}).get('evidence_id') for r in previous.get('pdf_references', [])}
        if previous.get('answer_status') == 'answered':
            for source in previous.get('sources', [])[:24]:
                if source.get('source_id') in allowed:
                    try:
                        resources.course.verify_source(bound, source)
                        if ((source['document_id'], source['version']) in bound.documents and
                            sum(len(s['text']) for s in resources.attached_sources) + len(source['text']) <= TEXT_LIMIT):
                            resources.attached_sources.append(source)
                    except (OSError, ValueError, KeyError):
                        pass
                    if len(resources.attached_sources) >= 4:
                        break
    return resources, (*readonly_tools(resources), ReaderGotoTool(request.task_revision or 1))


def structured_gate(kind):
    def gate(text, result):
        expected = STRUCTURED_TOOL[kind]
        rows = [r for r in result.tool_outputs if r.get('tool') == expected]
        if not rows:
            return False, '本轮没有成功读取所需状态，请先调用 ' + expected + '。'
        value = rows[-1]['data']
        if kind == 'outline':
            lines = [f"教材目录（本次列出 {len(value['items'])}/{value['total']} 个目标）："]
            lines += [f"- {r['chapter_title']} · {r['section_title']} · {r['title']}" for r in value['items']]
            if value['truncated']:
                lines += ['目录尚未列完，可继续查看。']
        elif kind == 'catalog':
            lines = [f"本次授权公开教材文档共 {value['total']} 份（按章阅读 PDF），匹配 {value['matched']} 份，本次列出 {value['listed']} 份。"]
            lines += [f"- {r['name']}（{r['page_count']} 页）" for r in value['items']]
        elif kind == 'personal_state':
            labels = {'answer_length': ('回答长度', '简短', '详细'),
                'example_density': ('举例数量', '少量', '较多'), 'learning_pace': ('讲解节奏', '慢一些', '紧凑一些'),
                'explanation_order': ('讲解顺序', '结论优先', '情境优先'),
                'question_frequency': ('主动提问频率', '少一些', '多一些'),
                'teaching_sequence': ('讲练顺序', '可先练习', '先讲后练'),
                'style_suggestions': ('风格建议', '少一些', '多一些')}
            lines = ['已确认的讲解偏好：'] if value['known'] else ['目前没有已确认的相关画像或偏好记录，不据此推断你的基础。']
            for key, strength in value['known'].items():
                name, low, high = labels[key]
                lines.append(f'- {name}：{low if strength < .34 else high if strength > .66 else "适中"}')
        else:
            lines = [f"已请求打开教材阅读版第 {value['action']['page']} 页，页面到达后再确认。"]
        result._publication = {'reply': '\n'.join(lines), 'pdf_references': [],
                               'textbook_sources': [], 'publication_kind': kind}
        return True, ''
    return gate


def skill_catalog(root, course_id):
    from agents.tools.skill_tools import _skills, _read
    allowed = {'reasoning-diagrams', 'experimental-design'} if course_id == 'experimental-psychology-3' else {'reasoning-diagrams', 'finite-structures'}
    rows = []
    for name in _skills(root):
        if name in allowed:
            text, _ = _read(root, name, 'SKILL.md')
            description = next((line.strip() for line in text.splitlines() if line.strip() and not line.startswith(('#', '---'))), '')
            rows.append(f'- {name}: {description[:180]}')
    return '\n可读取的当前课程技能（技能不是教材事实依据，也不代表已生成图解）：\n' + '\n'.join(rows) if rows else ''


class ReaderGotoTool(_ReadTool):
    definition = DEFINITIONS['reader_goto']
    scopes = SCOPES['reader_goto']
    read_only = True

    def __init__(self, revision):
        self.revision = revision

    def read(self, args, context, resources):
        from uuid import uuid5, NAMESPACE_URL
        from knowledge.pdf_reader import document
        has_source = 'source_id' in args
        if (has_source and set(args) - {'source_id', 'quote'} or
            not has_source and not {'document_id', 'version', 'page'} <= args.keys()):
            raise ReadFailure('invalid_arguments', '使用一个来源ID或文档、版本与页码。')
        if has_source:
            source = resources.source_index.get(args['source_id'])
            if not source:
                raise ReadFailure('unknown_source', '本任务没有该教材来源。')
            docid, version, page = source['document_id'], source['version'], source['page']
        else:
            docid, version, page = args['document_id'], args['version'], args['page']
        record = document(docid)
        if ((docid, version) not in resources.binding.documents or not record or
            type(page) is not int or not 1 <= page <= record['page_count']):
            raise ReadFailure('invalid_range', '页码或文档版本不属于本次授权。')
        rects = []
        quote = args.get('quote', '')
        if quote:
            from knowledge.citation_index import LiveCitationIndex
            index = LiveCitationIndex()
            try:
                located = index.locate(docid, version, quote)
                if located['status'] == 'exact' and {r['page'] for r in located['rects']} == {page}:
                    rects = located['rects']
            finally:
                index.close()
        sections = [s for s in record['sections'] if s['page'] <= page]
        section = sections[-1] if sections else record['sections'][0]
        token = json.dumps([context.task_id, self.revision, docid, version, page, quote], ensure_ascii=False)
        action = {'action_id': str(uuid5(NAMESPACE_URL, token)), 'task_id': context.task_id,
            'session_id': context.session_id, 'execution_revision': self.revision,
            'document_id': docid, 'version': version, 'page': page,
            'chapter_id': record['chapter_id'], 'section_id': section['id'],
            'rects': rects, 'quote': quote if rects else '', 'status': 'requested'}
        return {'kind': 'reader_action', 'action': action}, []
