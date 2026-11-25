"""自动入口只生成原生能力请求，不承担教学策略或模型执行循环。"""
import json

from .product_surface import CHAT_CAPABILITIES
AUTO_CAPABILITIES = CHAT_CAPABILITIES

async def choose_options(app,request):
    from deeptutor.runtime.capability_routing import route_explicit_quiz_request
    from deeptutor.runtime.request_contracts import validate_capability_config
    from deeptutor.services.llm import get_llm_client
    from deeptutor.services.llm.metrics import TurnUsage,current_usage
    from deeptutor.utils.json_parser import parse_json_response
    if request.capability!='chat' or request.auto_route is not True or request.workspace_mode:
        return {'options':{},'route':None}
    original=route_explicit_quiz_request(request.content,request.capability,enabled=True,workspace_mode=request.workspace_mode)
    if original is not None:
        return {'options':{},'route':{key:value for key,value in original.as_metadata().items()
            if key in ('requested_capability','capability','strategy','auto_routed')}}
    manifests=app.capabilities.get_manifests()
    choices=[{key:item[key] for key in ('name','description','request_schema','config_defaults') if key in item}
        for item in manifests if item['name'] in AUTO_CAPABILITIES
        and app.get_capability_availability(item['name'],manifests=manifests).available]
    names={item['name'] for item in choices}
    system=('你是统一入口的原生能力请求适配器。只返回JSON对象，不调用工具，不回答课程问题。'
        '格式：{"capability":"目录中的name","config":{},"mastery_session_mode":null}。'
        '手动能力由外层保留；这里只依据本轮用户消息选择。普通解释、Word/文件制作、多步骤多种交付选chat，'
        '由原生聊天工具组合处理。要求直接制定学习计划、目标、重点、时间步骤以及确认偏好后交付计划正文，均选chat；'
        '课程导航、掌握学习和教材伴读由各自页面进入，不在主聊天自动选择。'
        '明确要求深入研究/研究报告选deep_research，config必须提供原生mode和depth；'
        '未明确研究形式/深度时使用notes和standard。'
        '明确交互图示才选visualize。'
        '不确定时选chat，让原生ask_user按需要澄清；不要编造资料、权限、技能或配置字段。'
        'config严格遵守所选能力的request_schema。能力目录：'+json.dumps(choices,ensure_ascii=False))
    usage=TurnUsage(session_id=request.session_id,turn_id=request.request_id,source='capability_route')
    token=current_usage.set(usage)
    try:
        answer=await get_llm_client().complete(request.content,system_prompt=system,temperature=0.0,max_tokens=1024)
    finally:
        current_usage.reset(token)
    value=parse_json_response(answer,fallback=None)
    if not isinstance(value,dict) or value.get('capability') not in names:
        raise ValueError('自动入口未返回有效原生能力')
    capability=value['capability']
    options={'capability':capability,'config':validate_capability_config(capability,value.get('config') or {}),
        'capability_once':True}
    if capability=='mastery_path' and value.get('mastery_session_mode') is not None:
        mode=value['mastery_session_mode']
        if mode not in ('outline','study','review'):
            raise ValueError('自动入口学习模式无效')
        options['mastery_session_mode']=mode
    return {'options':options,'route':{'requested_capability':'chat','capability':capability,
        'strategy':'native_registry_intent','auto_routed':capability!='chat','usage_summary':usage.summary()}}
