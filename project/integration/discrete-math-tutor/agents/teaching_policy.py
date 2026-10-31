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
import re
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


# 13 个库 id 是唯一权威；下面只是历史/运行时别名，不新增策略。
# feedback 只保证可归一，部分正确与明确错误由调用方按 verdict 细分。
STRATEGY_ALIASES = {
    "explain": "direct_explanation",
    "contrast": "conceptual_comparison",
    "break_down": "scaffolding",
    "prerequisite": "scaffolding",
    "guided_practice": "socratic_questioning",
    "feedback": "guided_revision",
    "error_based_learning": "counterexample",
    "progressive_hinting": "hint",
}


def canonical_strategy(value: str) -> str:
    """归一策略名；未知名原样返回，由调用方按各自白名单拒绝。"""
    name = str(value or "").strip()
    return STRATEGY_ALIASES.get(name, name)


def accepted_strategy_names() -> List[str]:
    """校验用：库 id + 历史别名。"""
    return [*strategy_ids(), *STRATEGY_ALIASES]


def resolve_teaching_mode(message: str) -> str:
    """只解析本轮明确教法；不读写画像，也不增加模型调用。"""
    matches = []
    patterns = {
        "direct": r"直接(?:告诉我|解释|讲解|讲|给我(?:完整)?答案)|完整(?:解释|讲解|解答)|查看完整(?:解释|解答)|只讲不考|(?:不要|不用|别)(?:再)?(?:引导|提示)",
        "guided": r"引导我|带我(?:思考|推理)|一步步(?:引导|问我)|(?:不要|不用|别)(?:再)?直接(?:告诉我|给我(?:完整)?答案)|只给提示|只要提示|第?[123一二三]级提示|再给(?:一个|一点|一条)?提示|给我(?:一个|一点|一条)?提示",
        "practice": r"考考我|分步练习|(?:给我|出)(?:一道|一套|几道|个)?(?:练习题|题)|(?:开始|现在|我想)(?:做题|练习)",
        "review": r"备考复习|考前复习|考试复习|复习模式|(?:帮我|带我|请)复习",
    }
    for mode, pattern in patterns.items():
        for match in re.finditer(pattern, message):
            if re.search(r"(?:不要|不用|别|不想|不需要|不必|无需|不得|不给|不)(?:再)?$", message[:match.start()]):
                continue
            matches.append((match.start(), mode))
    return max(matches)[1] if matches else "auto"


def teaching_mode_instructions(mode: str) -> str:
    """教学风格与outline/study/review路径生命周期分别管理。"""
    return {
        "auto": "",
        "direct": "本轮直接讲解：完整回应当前问题，不先考学生，不以提示或反问代替答案，也不主动追加检查题；仅提示范围及来源核验仍须遵守。",
        "guided": "本轮引导探索：仅围绕学生当前询问的对象，先给一个必要提示或推理支架，再邀请学生完成一个有效步骤；不另引入新知识点或追加第二个要求，不同轮给完整答案。仅要求提示时不追加作答任务；明确禁止提问时用陈述式提示。",
        "practice": "本轮分步练习：围绕当前目标安排一个可作答步骤，题目放在最后并停止，不同轮公开答案；已有待答题优先复用，不能覆盖或重复登记。",
        "review": "本轮备考复习：组织概念关系、易混点和必要方法；重点注明教材、考纲/教师标注或教学建议的依据，不从图谱中心性推断考试分值。未经要求不强制测试，不据此改变学习路径或正式掌握状态。",
    }[mode]


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

    # 独立规则题提示的技能缺口只作为复习与诊断方向，不能冒充已确认误区。
    weak_skills=[item for item in state.skill_states if item.get("needs_review")]
    if weak_skills:
        strategies += ["scaffolding", "retrieval_practice"]
        difficulty = "easy"
        notes.append("最近独立规则题提示待复习技能：" + "、".join(item["name"] for item in weak_skills[:3]) +
            "；先围绕这些技能复习/检查。技能估计未校准，错误原因和具体误区仍待诊断，不能据此认定全章已掌握。")

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

    # 10) 来源明确的同条件策略观察只作为建议，不覆盖当前教学约束。
    if profile is not None and profile.teaching_effectiveness:
        notes.append("同知识点、难度和提示条件的弱策略权重（非因果效果）：" + str(profile.best_strategies(3)))

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
        "notes": "；".join(notes) if notes else "从当前教材概念的小问题开始",
    }
