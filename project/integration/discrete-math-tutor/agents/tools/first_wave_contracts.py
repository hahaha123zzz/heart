"""首批工具的封闭参数契约；reader_goto 仅供集成方接线，不提供假执行。"""
from agents.tools.protocol import ToolDefinition


TEXT_LIMIT = 12000
MEMORY_LIMIT = 4000
MAX_SOURCES = 24


def _definition(name, description, properties, required=(), **constraints):
    return ToolDefinition(name, description, raw_parameters={
        'type': 'object', 'properties': properties, 'required': list(required),
        'additionalProperties': False, **constraints})


ID = {'type': 'string', 'minLength': 1, 'maxLength': 200}
PAGE = {'type': 'integer', 'minimum': 1}
DOCUMENT_LOCATOR = {
    'document_id': ID, 'version': ID, 'page': PAGE,
    'end_page': PAGE,
}
LOCATOR_RULES = [
    {'required': ['unit_id'], 'not': {'anyOf': [{'required': [k]} for k in DOCUMENT_LOCATOR]}},
    {'required': ['document_id', 'version', 'page'], 'not': {'anyOf': [
        {'required': [k]} for k in ('unit_id', 'block_offset', 'char_offset')]}},
]
DEFINITIONS = {
    'material_outline': _definition('material_outline',
        '读取当前授权教材的真实目录；返回稳定目标ID、版本与续读位置，不改变学习计划。', {
            'chapter_id': PAGE, 'offset': {'type': 'integer', 'minimum': 0},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50}}),
    'read_material': _definition('read_material',
        '按目录目标ID或绑定文档的阅读版页码读取原文；最多一个目标或相邻三页。引用使用返回编号。', {
            'unit_id': ID, 'block_offset': {'type': 'integer', 'minimum': 0},
            'char_offset': {'type': 'integer', 'minimum': 0},
            **DOCUMENT_LOCATOR}, oneOf=LOCATOR_RULES),
    'read_source': _definition('read_source',
        '读取本任务已经登记的来源；expand=true补读同小节相邻段落，新的范围重新核验。不要编造ID。', {
            'source_id': ID, 'expand': {'type': 'boolean'}}, ['source_id']),
    'read_memory': _definition('read_memory',
        '只读当前学生已记录画像及明确确认的偏好；缺失不推断，不更新记忆。', {
            'section': {'type': 'string', 'enum': ['profile', 'preferences']}}),
    'kb_files': _definition('kb_files',
        '按公开教材文档清单盘点，不用检索片段数代替文档数；支持名称子串或glob。', {
            'pattern': {'type': 'string', 'maxLength': 100},
            'offset': {'type': 'integer', 'minimum': 0},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}),
    'reader_goto': _definition('reader_goto',
        '请求定位合法教材来源或阅读版页码；仅收到真实页面applied回执后才可声称到达。', {
            'source_id': ID, 'document_id': ID, 'version': ID, 'page': PAGE,
            'quote': {'type': 'string', 'maxLength': 500}}, oneOf=[
                {'required': ['source_id'], 'not': {'anyOf': [
                    {'required': [k]} for k in ('document_id', 'version', 'page')]}},
                {'required': ['document_id', 'version', 'page'], 'not': {'required': ['source_id']}}]),
}
SCOPES = {
    'material_outline': ('course:read',), 'read_material': ('course:read',),
    'read_source': ('course:read', 'sources:read'), 'read_memory': ('memory:read',),
    'kb_files': ('course:read',), 'reader_goto': ('reader:navigate',),
}
