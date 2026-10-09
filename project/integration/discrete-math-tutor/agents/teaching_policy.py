"""Teaching Policy —— 把"学生状态 + 长期画像 + 当前计划"映射为"教学策略约束"。

【自主衔接 / 本项目核心原创点】LLM 负责语言，Policy 负责教学决策。
输入现在有三方：Learning State + Learner Profile + 知识点计划。
- 策略名称来自教育学 / ITS 研究（Socratic / Scaffolding / Worked Example / …）；
- 节奏规则参考 OATutor（mastery-driven pacing）；
- 长期画像参考 GenMentor / LearningMAP（按教学有效性加权）。
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from models.learner_profile import LearnerProfile
from models.lesson_plan import LessonStep
from models.student_state import StudentState

_LIBRARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge",
    "teaching_strategies.json",
)


def load_library() -> List[Dict]:
    """加载教学策略库（13 种教学动作，来源见库文件注释）。"""
    try:
        with open(_LIBRARY_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return list(data.get("strategies") or [])
    except (OSError, ValueError):
        return []


def strategy_ids() -> List[str]:
    return [item["id"] for item in load_library()]


KNOWN_STRATEGIES = [
    "socratic_questioning",
    "scaffolding",
    "worked_example",
    "self_explanation",
    "retrieval_practice",
    "conceptual_comparison",
    "error_based_learning",
    "progressive_hinting",
]


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def select_policy(
    state: StudentState,
    current_step: Optional[LessonStep] = None,
    profile: Optional[LearnerProfile] = None,
) -> Dict:
    gap = state.calibration_gap
    strategies: List[str] = []
    notes: List[str] = []
    difficulty = "medium"
    action = "ask_question"
    hint_level = 1
    avoid = [
        "直接给出完整答案",
        "一次性讲解全部内容",
        "把一句话能说清的事拖成多轮",
        "为了提问而提问",
    ]

    # 1) 迷思概念：概念对比 + 错误样例
    if state.has_misconception:
        strategies += ["conceptual_comparison", "error_based_learning"]
        difficulty = "easy"
        notes.append("学生存在迷思概念：用对比/反例制造认知冲突，不要直接纠正")

    # 2) 掌握度低：样例学习 + 支架
    if state.mastery < 0.35:
        strategies += ["worked_example", "scaffolding"]
        difficulty = "easy"
        hint_level = max(hint_level, 2)
        notes.append("掌握度低：降低认知负荷，先示范再让学生复述")

    # 3) 困惑 / 挫败：支架 + 情绪支持
    if state.emotion in ("confused", "frustrated"):
        strategies += ["scaffolding"]
        difficulty = "easy"
        hint_level = max(hint_level, 2)
        notes.append("情绪低落或困惑：先给予情绪支持，把任务拆成更小步骤")

    # 4) 过度自信：提取练习 + 检验性提问
    if gap > 0.25:
        strategies += ["retrieval_practice", "socratic_questioning"]
        notes.append("过度自信：多用检验性问题，让学生自己发现漏洞")

    # 5) 信心不足：支架 + 具体正面反馈
    if gap < -0.25:
        strategies += ["scaffolding"]
        notes.append("信心不足但有一定基础：给予具体、可信的正面反馈")

    # 6) 无聊 / 已掌握：提高挑战
    if state.emotion == "bored" or state.mastery >= 0.75:
        strategies += ["retrieval_practice", "conceptual_comparison"]
        difficulty = "hard" if difficulty in ("easy", "medium") else difficulty
        notes.append("学生可能无聊或已掌握：提高挑战性")

    # 7) 元认知低：自我解释
    if state.metacognition < 0.4:
        strategies += ["self_explanation"]
        notes.append("元认知水平低：多让学生解释'你是怎么想到的'")

    # 8) 节奏控制（OATutor）：掌握较好 → 压缩节奏
    if state.mastery >= 0.7 and not state.has_misconception:
        strategies.insert(0, "retrieval_practice")
        if difficulty == "easy":
            difficulty = "medium"
        notes.append("掌握较好：压缩节奏，用检验任务快速确认后推进，不要重复讲解")

    # 9) 当前步骤约束（知识点短期计划）
    if current_step is not None:
        if current_step.suggested_strategy:
            strategies.insert(0, current_step.suggested_strategy)
        if current_step.teaching_form == "quiz":
            strategies.insert(0, "retrieval_practice")
        elif current_step.teaching_form == "explain":
            action = "explain"
        notes.append("围绕当前步骤目标：" + current_step.objective)

    # 10) 长期画像加权（GenMentor / LearningMAP）：什么对这位学生真正有效
    if profile is not None and profile.teaching_effectiveness:
        best = profile.best_strategies(3)
        notes.append("这位学生历史有效策略：" + str(best))
        for name, score in best:
            if name in KNOWN_STRATEGIES and score >= 0.6:
                strategies.insert(0, name)
        low = [
            name
            for name, score in profile.teaching_effectiveness.items()
            if score <= 0.3 and name in KNOWN_STRATEGIES
        ]
        if low:
            avoid.append("对这位学生效果差的策略：" + "、".join(low))

    if not strategies:
        strategies = ["socratic_questioning", "scaffolding"]

    if state.mastery < 0.3 and action == "ask_question":
        action = "give_example"

    return {
        "recommended_strategies": _dedupe(strategies),
        "avoid": avoid,
        "difficulty": difficulty,
        "action": action,
        "hint_level": hint_level,
        "notes": "；".join(notes) if notes else "从当前离散数学概念的小问题开始",
    }
