"""EXTRACT/KEYWORD/QUERY/VLM 使用宿主模型与调用预算。"""
from dataclasses import dataclass
from .config import HostModel,Metrics
from llm.client import LLMClient
@dataclass(frozen=True)
class RoleCall:
    config: HostModel
    owner: object = None
    max_async: int = 2
    timeout: int = 180

def resolve_query_roles(metrics=None):
    client=LLMClient(); meter=metrics or Metrics()
    calls={role:RoleCall(HostModel(client,meter,role)) for role in ("extract","keyword","query")}
    return calls
