"""TW1 独立工具；宿主通过 state['first_wave'] 注入每轮重新授权的只读服务。

这里不修改公共注册、事件或发布门禁。服务对象和来源索引不能保存进暂停快照。
"""
from copy import deepcopy
from dataclasses import dataclass, field
import json

from agents.q3_tools import _RETRIEVE_LOCK
from agents.tools.first_wave_contracts import DEFINITIONS, SCOPES, TEXT_LIMIT, MEMORY_LIMIT, MAX_SOURCES
from agents.tools.protocol import BaseTool, ToolResult
from agents.tools.validation import validate_arguments


class ReadFailure(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReadBinding:
    student_id: str
    session_id: str
    task_id: str
    course_id: str
    release_id: str
    documents: tuple[tuple[str, str], ...]


@dataclass
class ReadResources:
    binding: ReadBinding
    course: object = None
    memory: object = None
    source_index: dict = field(default_factory=dict)
    attached_sources: list = field(default_factory=list)

    def check(self, context):
        context.check_cancelled()
        b = self.binding
        if not all((b.student_id, b.session_id, b.task_id, b.course_id, b.release_id)) or (
            context.student_id, context.session_id, context.task_id) != (b.student_id, b.session_id, b.task_id):
            raise ReadFailure('binding_mismatch', '当前学生、会话或任务绑定已失效。')
        if self.course is not None:
            self.course.check(b)


def _identity(source):
    e = source.get('location', {}).get('evidence', {})
    return tuple(e.get(k) for k in ('document_id', 'document_version', 'source_block_id',
        'block_start', 'block_end', 'media_kind')) + (
        e.get('page') if e.get('source_block_id') is None else None, source.get('text'))


def register_sources(context, sources):
    """仅接收宿主已由Q2核验的来源；TW2须让retrieve_course也走此入口。"""
    resources = context.state.get('first_wave')
    if not isinstance(resources, ReadResources):
        raise ReadFailure('unavailable', '本轮没有绑定教材工具资源。')
    if not isinstance(sources, (list, tuple)) or len(sources) > MAX_SOURCES:
        raise ReadFailure('source_budget', '来源输入超过本轮允许数量。')
    with _RETRIEVE_LOCK:
        resources.check(context)
        proposed = deepcopy(resources.source_index)
        offset = max(int(context.state.get('source_offset', 0)),
                     max((s['index'] for s in proposed.values()), default=0))
        budget = min(MAX_SOURCES, max(1, int(context.state.get('max_sources', MAX_SOURCES))))
        output = []
        for value in sources:
            source = value.to_dict() if hasattr(value, 'to_dict') else deepcopy(value)
            if not isinstance(source, dict) or not isinstance(source.get('location'), dict):
                raise ReadFailure('unverified_source', '来源必须是可核验的结构化原文。')
            evidence = source.get('location', {}).get('evidence', {})
            doc = (source.get('document_id'), source.get('version'))
            if (doc not in resources.binding.documents or not source.get('source_id') or
                not source.get('text') or len(source['text']) > TEXT_LIMIT or
                evidence.get('document_id') != doc[0] or evidence.get('document_version') != doc[1] or
                evidence.get('quote') != source['text'] or evidence.get('evidence_id') != source['source_id']):
                raise ReadFailure('unverified_source', '来源缺少当前版本的Q2原文证据。')
            if resources.course is None:
                raise ReadFailure('unavailable', '本轮没有授权原文核验服务。')
            resources.course.verify_source(resources.binding, source)
            previous = next((s for s in proposed.values() if _identity(s) == _identity(source)), None)
            if previous is not None:
                output.append(deepcopy(previous))
                continue
            if source['source_id'] in proposed:
                raise ReadFailure('source_conflict', '同一来源ID对应不同原文范围。')
            if len(proposed) >= budget or offset >= budget:
                raise ReadFailure('source_budget', '本轮来源预算已用完，请使用已有证据。')
            offset += 1
            source['index'] = offset
            proposed[source['source_id']] = source
            output.append(deepcopy(source))
        context.check_cancelled()
        resources.source_index = proposed
        context.state['source_offset'] = offset
        context.state.setdefault('seen_source_ids', set()).update(proposed)
        return output


def restore_sources(context, sources):
    """暂停恢复只接受重新核验的原范围和原编号，不升级任意历史字符串。"""
    resources = context.state['first_wave']
    if len(sources) > MAX_SOURCES:
        raise ReadFailure('source_budget', '恢复来源超出预算。')
    indices = [s.get('index') for s in sources]
    if any(type(i) is not int or not 1 <= i <= MAX_SOURCES for i in indices) or len(set(indices)) != len(indices):
        raise ReadFailure('source_conflict', '恢复来源编号无效。')
    old_offset = context.state.get('source_offset', 0)
    context.state['source_offset'] = 0
    try:
        register_sources(context, sources)
        resources.source_index = {s['source_id']: deepcopy(s) for s in sources}
        context.state['source_offset'] = max(indices, default=0)
    except Exception:
        resources.source_index = {}
        context.state['source_offset'] = old_offset
        raise


class _ReadTool(BaseTool):
    read_only = True

    def run(self, arguments, context):
        context.check_cancelled()
        try:
            schema = self.definition.raw_parameters
            # 公共validator有保留参数豁免且不检查oneOf/数值边界，本地严格补齐。
            if not isinstance(arguments, dict) or set(arguments) - schema['properties'].keys():
                raise ReadFailure('invalid_arguments', '参数不在本工具白名单中。')
            checked = validate_arguments(self.definition, arguments, allow_unknown=False)
            if not checked.ok:
                raise ReadFailure('invalid_arguments', checked.message)
            args = checked.arguments
            for key, value in args.items():
                rule = schema['properties'][key]
                if value is None or (isinstance(value, str) and (
                    len(value) < rule.get('minLength', 0) or len(value) > rule.get('maxLength', 10000))):
                    raise ReadFailure('invalid_arguments', '参数值无效。')
                if isinstance(value, int) and not isinstance(value, bool) and not (
                    rule.get('minimum', value) <= value <= rule.get('maximum', value)):
                    raise ReadFailure('invalid_arguments', '参数超出允许范围。')
            r = context.state.get('first_wave')
            if not isinstance(r, ReadResources):
                raise ReadFailure('unavailable', '本轮没有绑定教材工具资源。')
            r.check(context)
            value, sources = self.read(args, context, r)
            context.check_cancelled()
            r.check(context)
            model_value = dict(value)
            if sources:
                model_value['text'] = '\n\n'.join(f"[{s['index']}] {s['text']}" for s in sources)
                model_value['citations'] = [{k: s.get(k) for k in (
                    'index', 'source_id', 'document_id', 'version', 'page')} for s in sources]
            return ToolResult(content=json.dumps(model_value, ensure_ascii=False), sources=sources,
                metadata={'tool': self.definition.name, 'result_kind': value['kind'], 'read_only': True, 'data': value})
        except ReadFailure as exc:
            return ToolResult(content=str(exc), success=False, metadata={'error': exc.code})
        except (OSError, LookupError, ValueError):
            return ToolResult(content='只读资源缺失、版本失效或范围无法核验，请重新绑定。',
                              success=False, metadata={'error': 'resource_invalid'})

    @staticmethod
    def course(r):
        if r.course is None:
            raise ReadFailure('unavailable', '当前没有授权教材。')
        return r.course


class MaterialOutlineTool(_ReadTool):
    definition = DEFINITIONS['material_outline']
    scopes = SCOPES['material_outline']

    def read(self, args, context, r):
        rows = self.course(r).outline(r.binding)
        if 'chapter_id' in args:
            rows = [row for row in rows if row['chapter_id'] == args['chapter_id']]
        offset, limit = args.get('offset', 0), args.get('limit', 50)
        end = min(len(rows), offset + limit)
        return {'kind': 'outline', 'items': rows[offset:end], 'total': len(rows),
            'truncated': end < len(rows), 'next_offset': end if end < len(rows) else None}, []


class ReadMaterialTool(_ReadTool):
    definition = DEFINITIONS['read_material']
    scopes = SCOPES['read_material']

    def read(self, args, context, r):
        unit = 'unit_id' in args
        if (unit and set(args) - {'unit_id', 'block_offset', 'char_offset'} or
            not unit and (not {'document_id', 'version', 'page'} <= args.keys() or
                          set(args) & {'block_offset', 'char_offset'})):
            raise ReadFailure('invalid_arguments', '只提供一个目标ID，或文档ID、版本与页码。')
        if not unit:
            if (args['document_id'], args['version']) not in r.binding.documents:
                raise ReadFailure('unauthorized_document', '文档不属于本轮授权版本。')
            end = args.get('end_page', args['page'])
            if not args['page'] <= end <= args['page'] + 2:
                raise ReadFailure('invalid_arguments', '每次最多读取相邻三页。')
        value, sources = self.course(r).read_material(r.binding, args, context.check_cancelled)
        if len(value['text']) > TEXT_LIMIT:
            raise ReadFailure('read_budget', '服务返回超过原文预算，不能静默截断证据。')
        rows = register_sources(context, sources)
        return dict(value, kind='textbook', citation_ids=[s['source_id'] for s in rows]), rows


class ReadSourceTool(_ReadTool):
    definition = DEFINITIONS['read_source']
    scopes = SCOPES['read_source']

    def read(self, args, context, r):
        source = r.source_index.get(args['source_id'])
        if source is None:
            raise ReadFailure('unknown_source', '该来源未在本任务中登记，请先检索或读取教材。')
        if not args.get('expand', False):
            self.course(r).check(r.binding)
            rows = register_sources(context, [source])
            return {'kind': 'textbook', 'text': source['text'], 'truncated': False,
                    'citation_ids': [source['source_id']]}, rows
        value, sources = self.course(r).read_source(r.binding, deepcopy(source), context.check_cancelled)
        if len(value['text']) > TEXT_LIMIT:
            raise ReadFailure('read_budget', '来源展开超过预算。')
        rows = register_sources(context, sources)
        return dict(value, kind='textbook', citation_ids=[s['source_id'] for s in rows]), rows


class ReadMemoryTool(_ReadTool):
    definition = DEFINITIONS['read_memory']
    scopes = SCOPES['read_memory']

    def read(self, args, context, r):
        if r.memory is None:
            raise ReadFailure('unavailable', '本轮没有绑定学生画像读取服务。')
        value = r.memory.read(r.binding.student_id, args.get('section', 'preferences'))
        if len(json.dumps(value, ensure_ascii=False)) > MEMORY_LIMIT:
            raise ReadFailure('read_budget', '画像响应超过预算，不能静默截断。')
        return dict(value, kind='personal_state'), []


class KbFilesTool(_ReadTool):
    definition = DEFINITIONS['kb_files']
    scopes = SCOPES['kb_files']

    def read(self, args, context, r):
        from fnmatch import fnmatchcase
        rows = self.course(r).files(r.binding)
        pattern = args.get('pattern', '').casefold()
        matched = [row for row in rows if not pattern or pattern in row['name'].casefold()
                   or fnmatchcase(row['name'].casefold(), pattern)]
        offset, limit = args.get('offset', 0), args.get('limit', 20)
        selected = matched[offset:offset + limit]
        end = min(len(matched), offset + len(selected))
        return {'kind': 'catalog', 'count_basis': 'authorized_public_documents', 'total': len(rows),
            'matched': len(matched), 'listed': len(selected), 'omitted': len(matched) - len(selected),
            'items': selected, 'next_offset': end if end < len(matched) else None}, []


def readonly_tools(resources):
    """返回真实资源可用的实例，交给既有build_registry(extra_tools/extra_scopes)。"""
    tools = []
    if resources.course is not None:
        tools.extend([MaterialOutlineTool(), ReadMaterialTool(), ReadSourceTool(), KbFilesTool()])
    if resources.memory is not None:
        tools.append(ReadMemoryTool())
    return tuple(tools)
