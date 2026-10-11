"""模型只提议具体误区变更，资格和状态迁移由服务器判断。"""
from typing import Literal
from pydantic import BaseModel, Field, StrictInt


class MisconceptionUpdate(BaseModel):
    misconception_id: StrictInt = Field(gt=0)
    action: Literal["resolve", "dismiss"]
    source_quote: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)
