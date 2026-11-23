"""在原生用户作用域内，把阅读器动作映射回宿主正式教材。"""


def reader_actions(events):
    from .course_reading import ensure_course_reading
    pending = []
    for event in events:
        metadata = event.get('metadata') or {}
        action = metadata.get('tool_metadata') or {}
        if (event.get('type') == 'tool_result' and metadata.get('tool') == 'reader_goto'
                and action.get('reader_action') == 'goto'):
            pending.append(action)
    if not pending:
        return []
    prepared = ensure_course_reading()
    materials = {item['material_id']: item for item in prepared['materials']}
    output = []
    for action in pending[-1:]:
        material = materials.get(action.get('material_id'))
        if material is None:
            raise ValueError('原生阅读动作没有对应的当前教材')
        output.append({'document_id': material['document_id'], 'version': material['version'],
            'page': action.get('locator'), 'quote': action.get('quote') or ''})
    return output
