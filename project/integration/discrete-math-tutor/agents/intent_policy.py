"""意图识别灰度配置；由服务端决定，不接受请求覆盖。"""
import os
from dataclasses import dataclass


def _flag(values, key, default="1"):
    value = values.get(key, default).strip().lower()
    if value not in {"0", "1", "false", "true"}:
        raise ValueError(f"{key}必须为0或1")
    return value in {"1", "true"}


@dataclass(frozen=True)
class IntentPolicy:
    scope: str = "all"
    students: frozenset[str] = frozenset()
    context: bool = True
    understanding: bool = True
    clarification: bool = True

    @classmethod
    def from_env(cls, values=None):
        values = os.environ if values is None else values
        scope = values.get("INTENT_ROLLOUT", "all").strip().lower()
        if scope not in {"all", "test", "allowlist", "off"}:
            raise ValueError("INTENT_ROLLOUT必须为all/test/allowlist/off")
        students = frozenset(s.strip() for s in values.get("INTENT_STUDENT_ALLOWLIST", "").split(",") if s.strip())
        if scope == "allowlist" and not students:
            raise ValueError("allowlist模式必须指定INTENT_STUDENT_ALLOWLIST")
        if _flag(values, "INTENT_REWRITE_ENABLED", "0"):
            raise ValueError("自由改写尚未实现，INTENT_REWRITE_ENABLED必须为0")
        return cls(scope, students, _flag(values, "INTENT_CONTEXT_ENABLED"),
                   _flag(values, "INTENT_TASK_ENABLED"), _flag(values, "INTENT_CLARIFICATION_ENABLED"))

    def enabled(self, student_id, account_type):
        allowed = (self.scope == "all" or self.scope == "test" and account_type == "test"
                   or self.scope == "allowlist" and student_id in self.students)
        return bool(allowed and self.context and self.understanding)

    def can_clarify(self, student_id, account_type):
        return self.enabled(student_id, account_type) and self.clarification
