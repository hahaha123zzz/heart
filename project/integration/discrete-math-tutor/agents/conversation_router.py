"""Conversation Router —— 判断学生这一轮"在做什么 / 在聊什么"，决定是否切换知识点。

【参考实现】
- ghdkim/tutor-agent：Classification Agent 判断 topic / level / goal 后路由到不同 Agent；
- TACT：Student-Move Taxonomy（question / attempt / statement / acknowledgement / off-task）。

【自主衔接】这是本项目此前缺失的一层。修的关键问题：
"知识点"不再等于 Tutor 的身份，而是**可切换的状态**；
非学习消息（寒暄/情绪/闲聊）不再被硬塞进当前知识点继续教。
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel

from llm.client import LLMClient

STUDENT_MOVES = [
    "question",  # 提问
    "attempt",  # 作答 / 尝试
    "statement",  # 陈述
    "acknowledgement",  # 确认 / 附和
    "off_task",  # 跑题 / 非学习
]
INTENTS = ["continue", "switch_topic", "new_goal", "off_task", "clarify_task"]


class RoutingResult(BaseModel):
    student_move: str = "statement"
    move_status: str = ""  # attempt 时为 adequate/partial/problematic，其余为空
    intent: str = "continue"
    topic: str = ""
    confidence: float = 0.5
    reason: str = ""


SYSTEM_PROMPT = """[AGENT:conversation_router]
你是 AI Tutor 的"对话路由器"。判断学生这句话现在属于什么任务，以及是否需要切换知识点。
只输出 JSON：
{
  "student_move": "question|attempt|statement|acknowledgement|off_task",
  "move_status": "attempt 时填 adequate|partial|problematic，其余填空字符串",
  "intent": "continue|switch_topic|new_goal|off_task|clarify_task",
  "topic": "若切换话题或新目标，写出目标知识点（简短名词短语）；否则空字符串",
  "confidence": 0.0到1.0,
  "reason": "一句话依据"
}
判定规则：
1. 学生明确表示要换话题，或问的是与当前知识点明显无关的新领域 -> intent=switch_topic，并给出 topic；
2. 学生提出一个全新的学习目标 -> intent=new_goal，并给出 topic；
3. 学生只说"想换个话题/聊点别的"但没说换成什么 -> intent=clarify_task，topic 留空；
4. 学生只是问候、寒暄、表达情绪（累/烦/开心）、道谢，或表示今天到此为止/下课/不想学了，
   不是学习任务 -> intent=off_task；
5. 其余围绕当前知识点的提问/作答/陈述 -> intent=continue。
重要：不要因为一句话里偶然出现某个词就切换；只有学生确实在转移任务或话题时才切换。
不要因为学生提了一个与当前知识点相关的新疑问就切换——那属于 continue。"""


class ConversationRouter:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def route(
        self,
        student_input: str,
        knowledge_point: str,
        history: List[Dict[str, str]],
        known_points: List[str],
    ) -> RoutingResult:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "当前知识点：" + (knowledge_point or "（无）") + "\n"
                    "该学生学过的知识点：" + str(known_points) + "\n"
                    "最近对话：" + str(history[-4:]) + "\n"
                    "学生最新输入：" + student_input
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        return self._validate(data)

    @staticmethod
    def _validate(data: Dict) -> RoutingResult:
        move = data.get("student_move")
        if move not in STUDENT_MOVES:
            move = "statement"
        status = str(data.get("move_status") or "").strip().lower()
        if move != "attempt" or status not in ("adequate", "partial", "problematic"):
            status = ""
        intent = data.get("intent")
        if intent not in INTENTS:
            intent = "continue"
        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        return RoutingResult(
            student_move=move,
            move_status=status,
            intent=intent,
            topic=str(data.get("topic") or "").strip(),
            confidence=max(0.0, min(1.0, confidence)),
            reason=str(data.get("reason") or ""),
        )
