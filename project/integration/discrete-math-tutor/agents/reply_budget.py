"""生成与核验共用表达要求：不设字数上限，也不能以字数截断替代完整回答。"""
import os
import re
from dataclasses import dataclass

ANSWER_MAX_TOKENS = 8000


def requests_proof_overview(text):
    return bool(re.search(r"(?:完整|全部).*证明|证明.*(?:完整|全部|思路|路线)", text))


def requests_supplementary_proof(text):
    return bool(re.search(r"证明|推导", text) and re.search(r"补充|补上|如果没有|教材.*(?:未写|未给|没有)", text))


@dataclass(frozen=True)
class ReplyBudget:
    target: int | None = None
    maximum: int | None = None

    @property
    def max_tokens(self):
        # 仅作模型 API 技术上限，不是回答字符门禁。
        try:
            return int(os.getenv("ANSWER_MAX_TOKENS", str(ANSWER_MAX_TOKENS)))
        except (TypeError, ValueError):
            return ANSWER_MAX_TOKENS

    def instructions(self):
        return ("不设字数上限。按问题需要完整回答，优先保证结构、覆盖、依据和可执行性；"
                "避免重复铺垫；不得为缩短而漏答对象、条件、结论或引用。")


def reply_budget(text="", *, preferences=None, execution=None, action="explain", question_options=False,
                 feedback_mode="", proof_overview=False, supplementary_proof=False, comparison=False, proof=False):
    # 参数只为兼容现有调用；长度不再参与生成或核验。
    return ReplyBudget()
