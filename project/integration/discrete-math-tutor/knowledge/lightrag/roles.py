"""EXTRACT/KEYWORD/QUERY/VLM 使用宿主模型与调用预算。"""
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit
from .config import HostModel,Metrics
from llm.client import LLMClient
@dataclass(frozen=True)
class RoleCall:
    config: HostModel
    owner: object = None
    max_async: int = 2
    timeout: int = 180

def resolve_query_roles(metrics=None):
    if path := os.getenv('LIGHTRAG_QUERY_ENV_FILE'):
        from dotenv import dotenv_values
        values=dotenv_values(Path(path))
        endpoint=values.get('OPENAI_BASE_URL','')
        url=urlsplit(endpoint)
        if (url.scheme!='https' or url.netloc!='api.deepseek.com' or url.path.rstrip('/') not in ('','/v1')
                or url.query or url.fragment or not values.get('DEEPSEEK_API_KEY')):
            raise ValueError('显式查询配置需要DeepSeek官方地址和专用配置文件中的key')
        client=LLMClient(api_key=values['DEEPSEEK_API_KEY'],base_url=endpoint,
                         model=values.get('DEEPSEEK_MODEL','deepseek-flash'),mock=False)
    else:
        client=LLMClient()
    meter=metrics or Metrics()
    calls={role:RoleCall(HostModel(client,meter,role)) for role in ("extract","keyword","query")}
    return calls


def query_binding(expected, calls):
    """仅显式允许同模型切到官方查询；建图身份与嵌入校验保持独立。"""
    indexed=expected['extract'];current=calls['extract'].config.identity
    changed={key for key in set(indexed)|set(current) if indexed.get(key)!=current.get(key)}
    if changed and (changed!={'endpoint'} or not os.getenv('LIGHTRAG_QUERY_ENV_FILE')
                    or current['endpoint'] not in ('https://api.deepseek.com','https://api.deepseek.com/v1')):
        raise RuntimeError('模型配置已变化，需要核对候选策略')
    return {'mode':'official_deepseek_query' if changed else 'matching_index_model',
            'indexed_extract':dict(indexed),'query':calls['query'].config.identity,
            'keyword':calls['keyword'].config.identity,'query_only':True}
