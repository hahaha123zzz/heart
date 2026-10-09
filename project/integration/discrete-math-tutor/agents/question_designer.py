"""Question Designer —— 诊断性问题设计（问题设计与语言生成解耦）。

【参考实现】
- "BKT + Misconception Diagnosis"类项目：问题与 misconception 绑定，
  生成"能区分学生是否仍然存在误解 X"的问题，而不是随便出题；
- MCQ distractor 生成项目（如 Leaf-Question-Generation）：
  每个干扰项对应一种具体误解，看起来都要有道理。

【自主衔接】输出结构化 Question Spec，交给 Response Generator 说成自然语言；
Quality Checker 按 spec 校验生成出来的题目。这样"出什么题"由我们控制，
"怎么说出来"才交给 LLM。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agents.teaching_planner import TeachingPlan
from knowledge.retriever import retrieve_knowledge
from llm.client import LLMClient
from models.lesson_plan import LessonStep
from models.student_state import StudentState

ALLOWED_QUESTION_TYPES = [
    "scenario_judgment",
    "error_analysis",
    "prediction",
    "transfer",
    "open_explanation",
    "mcq",
]


class QuestionOption(BaseModel):
    text: str = ""
    maps_to: Optional[str] = None  # 该选项对应的误解（正确选项为 null）
    correct: bool = False


class QuestionSpec(BaseModel):
    question_type: str = "open_explanation"
    target_misconception: Optional[str] = None
    discrimination_goal: str = ""  # 这道题要区分学生会什么/不会什么
    stem: str = ""
    options: List[QuestionOption] = []
    acceptable_free_answer: str = ""


SYSTEM_PROMPT = """[AGENT:question_designer]
你是 AI Tutor 的"问题设计师"。你的任务不是出任意题目，而是设计"诊断性问题"：
能够区分学生是否仍然存在目标误解。
硬性要求：
1. 针对 target_misconception（或当前步骤的完成标准）设计；
   学生答错时，要能定位到具体是哪种误解；
2. 禁止一眼就能答对的二选一；
3. 若给选项：必须 3 到 4 个，每个干扰项对应一种具体误解或错误思路，
   且看起来都有道理，选项长度与风格相近，禁止明显正确或明显荒谬的选项；
4. 优先使用：情境判断、找错、预测、迁移应用、开放式解释；
5. 难度符合 difficulty：简单=直接辨析，中等=新情境，难=迁移应用；
6. 干扰项要像"真实易犯的错误"一样有吸引力（Chain-of-Exemplar 原则）：
   至少一个强干扰项看起来很像正确答案，禁止用明显荒谬的选项凑数；
7. 所有文字字段尽量简短（避免输出被截断）：
   target_misconception ≤ 25 字，discrimination_goal ≤ 30 字，每个 option.text ≤ 30 字。
8. 题目与标准答案必须能由离散数学教材摘录核验；摘录不足时只问基础概念，不编造公式。
只输出 JSON：
{
  "question_type": "scenario_judgment|error_analysis|prediction|transfer|open_explanation|mcq",
  "target_misconception": "针对的误解，无则 null",
  "discrimination_goal": "这道题要区分学生会什么/不会什么",
  "stem": "题干",
  "options": [{"text": "...", "maps_to": "误解或 null", "correct": true}],
  "acceptable_free_answer": "开放式作答时可接受的要点"
}"""


class QuestionDesigner:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def design(
        self,
        state: StudentState,
        plan: TeachingPlan,
        current_step: Optional[LessonStep] = None,
        textbook_excerpts: str = "",
    ) -> QuestionSpec:
        step_text = (
            str(current_step.model_dump()) if current_step else "无（课程已完成或未规划）"
        )
        catalog = retrieve_knowledge(state.current_concept or state.misconception or "")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "学生状态：" + str(state.model_dump()) + "\n"
                    "教学计划：" + str(plan.model_dump()) + "\n"
                    "当前课程步骤：" + step_text + "\n"
                    "已知误解目录（供参考，也可补充新误解）：" + str(catalog)
                    + "\n离散数学教材摘录：" + textbook_excerpts
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        return self._validate(data)

    @staticmethod
    def _validate(data: Dict[str, Any]) -> QuestionSpec:
        question_type = data.get("question_type")
        if question_type not in ALLOWED_QUESTION_TYPES:
            question_type = "open_explanation"
        options: List[QuestionOption] = []
        for item in (data.get("options") or [])[:4]:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            options.append(
                QuestionOption(
                    text=str(item["text"]),
                    maps_to=item.get("maps_to"),
                    correct=bool(item.get("correct")),
                )
            )
        return QuestionSpec(
            question_type=question_type,
            target_misconception=data.get("target_misconception"),
            discrimination_goal=str(data.get("discrimination_goal") or ""),
            stem=str(data.get("stem") or ""),
            options=options,
            acceptable_free_answer=str(data.get("acceptable_free_answer") or ""),
        )
