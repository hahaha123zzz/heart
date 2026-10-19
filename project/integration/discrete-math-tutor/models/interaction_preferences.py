"""用户确认的风格参数；临时覆盖不写入学习画像。"""
from pydantic import BaseModel, ConfigDict, Field


class InteractionPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer_length: float | None = Field(None, ge=0, le=1, strict=True)
    example_density: float | None = Field(None, ge=0, le=1, strict=True)
    learning_pace: float | None = Field(None, ge=0, le=1, strict=True)
    explanation_order: float | None = Field(None, ge=0, le=1, strict=True)
    question_frequency: float | None = Field(None, ge=0, le=1, strict=True)
    style_suggestions: float | None = Field(None, ge=0, le=1, strict=True)


def style_instructions(values):
    lines = ["用户已确认的交互偏好（本轮明确要求、仅提示范围和教材准确性优先）："]
    if "answer_length" in values:
        lines.append("回答简短，保留必要条件。" if values["answer_length"] < .34 else "详细解释关键步骤。" if values["answer_length"] > .66 else "回答长度适中。")
    if "example_density" in values:
        lines.append("多用相关辅助例子并标注非原书例题。" if values["example_density"] > .66 else "例子仅在必要时使用。" if values["example_density"] < .34 else "适量举例。")
    if "learning_pace" in values:
        lines.append("放慢节奏，一次聚焦一个要点。" if values["learning_pace"] < .34 else "减少重复铺垫，紧凑推进。" if values["learning_pace"] > .66 else "按正常节奏推进。")
    if "explanation_order" in values:
        lines.append("先给结论，再解释依据。" if values["explanation_order"] < .34 else "本轮先给一个简短情境，标注‘辅助例子（非原书例题）’，再归纳概念和依据；不要先写完整定义。若本轮是仅提示，情境也不得泄露答案；若用户明确指定其他顺序或要求练习，优先完成本轮要求。" if values["explanation_order"] > .66 else "按问题选择讲解顺序。")
    if "question_frequency" in values:
        lines.append("不主动追加检查题或理由追问；用户本轮明确要求练习时仍完成练习。" if values["question_frequency"] < .34 else "适合时可邀请一次简短理解检查，不能每轮强制答题。" if values["question_frequency"] > .66 else "仅在必要时检查理解。")
    lines.append("不能声称已替用户修改偏好；风格调整须由界面上的用户确认完成。")
    return "\n".join(lines)
