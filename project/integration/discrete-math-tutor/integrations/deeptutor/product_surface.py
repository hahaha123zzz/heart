"""学生产品已验收的入口范围；隐藏不删除上游实现或历史数据。"""
CHAT_CAPABILITIES = frozenset(('chat', 'deep_question', 'visualize', 'deep_solve', 'ask_questions', 'deep_research'))
WORKSPACE_CAPABILITIES = frozenset(('mastery_path', 'immersive_reading', 'course_study'))
ENABLED_CAPABILITIES = CHAT_CAPABILITIES | WORKSPACE_CAPABILITIES
ENABLED_SKILLS = frozenset(('docx',))
UNVERIFIED_TOOLS = frozenset(('web_search', 'paper_search', 'zotero_search', 'preprint',
    'research_lit', 'research_audit', 'web_fetch', 'github', 'imagegen', 'videogen',
    'geogebra_analysis', 'consult_subagent', 'load_tools', 'knowledge_frontier'))


def validate_options(options):
    if options.get('capability', 'chat') not in ENABLED_CAPABILITIES:
        raise ValueError('该能力尚未在当前课程开放')
    if set(options.get('tools') or ()) & UNVERIFIED_TOOLS:
        raise ValueError('所选工具尚未在当前课程开放')
    if set(options.get('skills') or ()) - ENABLED_SKILLS or options.get('mcp'):
        raise ValueError('所选扩展尚未在当前课程开放')
    if options.get('config', {}).get('render_mode', 'auto') not in ('auto', 'svg', 'chartjs', 'mermaid', 'mindmap', 'html'):
        raise ValueError('该图示类型尚未在当前课程开放')
