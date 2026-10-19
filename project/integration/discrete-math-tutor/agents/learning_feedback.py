"""Deterministic short-turn signals; never infer mastery from 'I don't know'."""

from __future__ import annotations

from typing import Iterable
import re


STUCK_PHRASES = ("不知道", "不懂", "没懂", "不会", "没思路", "看不懂", "不清楚")
UNDERSTOOD_PHRASES = ("懂了", "明白了", "理解了")

HINT_FEEDBACK_RULES = """提示以一个学习目标为单位，允许圈词后比较等连续操作，不要求机械地只有一个动词。
第1级指出疑点或教材位置；第2级给出方法或相似情境；第3级用简化情境示范一个中间步骤，再留一步让学生完成。后两级不能只重复上一轮的读定义/圈词。
允许引用学生错误原句、概念对象名称和定义位置，例如‘每名被试后面的数量词’。这些定位本身不是答案泄露；不得因出现对象名称或指出位置判错。
禁止公布当前任务最终数值、最终判断（仅提示时）或完整正确定义再让学生改词。相似情境不得变相给出当前题完整答案。
单一概念判断的禁止示例：‘教材说每名被试只接受一种水平，请再改一次’已经完整纠正了原判断，即使没写设计名称也算给出答案，必须拒绝。允许示例：‘查看每名被试后面的数量词，再对照你的原句’，没有公布正确数量，不算泄露。
只围绕当前疑点推进，不增加无关练习。"""


def is_stuck(text: str) -> bool:
    phrases = "|".join(map(re.escape, STUCK_PHRASES))
    # 双盲实验中的“被试不知道分组”描述实验条件，不是学生在求助。
    return bool(re.search(r"(?:^|我(?:还是|仍然|也|完全|真的|实在|一直|都|又|觉得)*|还是|仍然|完全)(?:" + phrases + r")", text.strip()))


def is_self_report_understood(text: str) -> bool:
    return not is_stuck(text) and bool(re.fullmatch(
        r"(?:(?:好(?:的)?|嗯|哦)[，,\s]*)?(?:我(?:现在|已经|大概|基本|终于)?|现在|已经|大概|基本|终于)?(?:懂了|明白了|理解了)(?:[，,]\s*(?:谢谢|感谢))?[。.!！\s]*", text.strip()))


def consecutive_stuck(history: Iterable[dict[str, str]], latest: str) -> int:
    if not is_stuck(latest):
        return 0
    count = 1
    for item in reversed(list(history)):
        if item.get("role") != "user":
            continue
        if not is_stuck(item.get("content", "")):
            break
        count += 1
    return count


def adapt_answer_feedback(plan, move, *, execution, diagnosis, previous_event, stuck_count, state, student_input, needs_context=False):
    """最终对齐后设置本轮反馈，历史只提供提示级别，不代替教材诊断。"""
    prior = (previous_event or {}).get("payload", {}).get("teaching_context", {})
    earlier = prior.get("answer_diagnosis") or prior.get("support_diagnosis") or {}
    repeated = (earlier.get("verdict") in ("incorrect", "partial") and diagnosis is not None
                and diagnosis.verdict in ("incorrect", "partial")
                and earlier.get("error_type") == diagnosis.error_type)
    same_support = prior.get("feedback_mode") in ("targeted_hint", "hint_only", "worked_example", "supportive_hint")
    previous_level = prior.get("hint_level", 0)
    previous_level = previous_level if type(previous_level) is int and 0 <= previous_level <= 3 else 0
    level = min(3, previous_level + 1) if same_support and (repeated or stuck_count or needs_context) else 1
    full_explanation = bool(re.search(r"完整|详细|直接.*(?:解释|答案|讲解|告诉)|请.*(?:解释|说明|讲解)|^(?:解释|说明|讲解)|为什么|为何|讲清楚", student_input))
    full_explanation = full_explanation or bool(set(execution.learning_intents) & {"proof", "compare", "summary"})
    if "practice" in execution.learning_intents and not execution.hint_only:
        return {}
    mode = ""
    instruction = ""
    if execution.verdict_only:
        mode, action, strategy, teaching_move = "verdict_only", "explain", "error_based_learning", "direct_correction"
        instruction = "只简短说明本次判断正确、部分正确、不正确或暂不能判断；不追加题目、提示任务或理由追问。只判断本次回答，不声称掌握。"
    elif execution.hint_only:
        mode, action, strategy, teaching_move = "hint_only", "give_hint", "progressive_hinting", "progressive_hinting"
        instruction = "只给一个提示，不给当前任务的最终判断或完整解法；即使连续卡住也不自动转完整讲解。前文已有待判定的具体判断时，不得用直接引述完整定义的方式给出等价答案，只给一个核对动作。"
    elif full_explanation and (diagnosis is not None or stuck_count) and (diagnosis is None or diagnosis.verdict != "unclear"):
        mode, action, strategy, teaching_move = "explain_feedback", "explain", "error_based_learning", "direct_correction"
        instruction = "先核对学生本轮原句，明确说明成立和不成立的部分，并依据教材完整解释理由；不把解释改成反问。"
    elif diagnosis is None and is_self_report_understood(student_input):
        mode, action, strategy, teaching_move = "check_self_report", "ask_question", "retrieval_practice", "retrieval_practice"
        instruction = "自然邀请学生做一个围绕刚讲过要点的小检查，直接呈现题目；开头可说“我们用一个小情境确认一下”，无须解释为什么检查，不评价学生能力，不复述平台内部判断规则。"
    elif diagnosis is not None and diagnosis.verdict == "unclear":
        mode, action, strategy, teaching_move = "clarify_attempt", "ask_question", "scaffolding", "guided_revision"
        instruction = "信息不足以判断对错；只问一个必要的澄清问题，不猜测学生结论，不把表达不清判成概念错误。"
    elif diagnosis is not None and diagnosis.verdict == "correct":
        mode, action, strategy, teaching_move = "confirm_and_reflect", "ask_question", "self_explanation", "self_explanation"
        instruction = "确认本次作答正确的具体依据，再围绕同一个判断问一个简短理由问题；不新增无关题，不断言学生已经掌握。"
    elif stuck_count >= 2 or (repeated and level >= 2):
        mode, action, strategy, teaching_move = "worked_example", "give_example", "worked_example", "worked_example"
        instruction = "前一提示未解决问题，换一个明确标注的辅助小例子。例子须解释学生原句的困惑或理由，不能只重述定义；涉及比较时说明哪些对象在什么条件下比较。随机分配不自动证明因果，无数据不能宣称实验效果。解释完成后邀请学生重述原判断，不重复同一句提示。"
    elif stuck_count or (diagnosis is not None and diagnosis.verdict in ("incorrect", "partial")):
        mode, action, strategy, teaching_move = "targeted_hint", "give_hint", "scaffolding", "guided_revision"
        instruction = "可以先简短指出本次判断不正确或条件不全，然后只定位原句中的一个疑点，给一个可执行的核对动作，请学生再尝试；不直接补出完整定义或正确方案，也不能把正确方案藏在条件句中。不给无关新任务。"
    if not mode:
        return {}
    if execution.no_questions:
        if action == "ask_question":
            mode, action, strategy, teaching_move = "explain_feedback", "explain", "error_based_learning", "direct_correction"
            instruction = "直接回应本轮已核验的判断和依据；信息不足时说明具体缺口，不猜测对错。"
        instruction += "不追加问题或要求学生回复；用户请求完整解释时仍须完整回应。"
    frustrated = state.emotion == "frustrated" or bool(re.search(r"越学越烦|好烦|挫败|有点烦|太难了", student_input))
    if frustrated:
        instruction = "先简短回应本轮困难，减小步子，不批评或推断心理状态。" + instruction
        if mode == "targeted_hint":
            mode = "supportive_hint"
    if action in ("give_hint", "give_example") or frustrated:
        plan.difficulty = move.difficulty = "easy"
    plan.action, plan.strategy, plan.hint_level = action, strategy, level
    move.action, move.instructional_move, move.hint_level = action, teaching_move, level
    move.rationale = plan.rationale = "按本轮作答诊断与已保存的提示级别反馈"
    levels = {1: "关注一个概念或条件", 2: "给出方法或相似例子的关键步骤", 3: "把当前疑点拆成一个最小操作；仍不替学生完成仅提示任务"}
    return {"mode": mode, "hint_level": level, "verification": "ai_provisional", "support_required": frustrated,
            "diagnosis": diagnosis.model_dump() if diagnosis else None,
            "support_diagnosis": (diagnosis.model_dump() if diagnosis else earlier) if mode in ("targeted_hint", "hint_only", "worked_example", "supportive_hint") and (diagnosis is not None or stuck_count or needs_context) else None,
            "instructions": instruction + (("本轮提示级别：" + levels[level]) if action in ("give_hint", "give_example") else "")}
