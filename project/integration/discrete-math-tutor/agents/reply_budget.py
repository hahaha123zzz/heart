"""生成与核验共用表达预算，不能以字数截断替代完整回答。"""
import re
from dataclasses import dataclass


def requests_proof_overview(text):
    return bool(re.search(r"(?:完整|全部).*证明|证明.*(?:完整|全部|思路|路线)", text))


def requests_supplementary_proof(text):
    return bool(re.search(r"证明|推导", text) and re.search(r"补充|补上|如果没有|教材.*(?:未写|未给|没有)", text))


@dataclass(frozen=True)
class ReplyBudget:
    target: int
    maximum: int

    @property
    def max_tokens(self):
        return 900 if self.target >= 480 else 700 if self.target >= 320 else 400

    def instructions(self):
        return (f"表达目标：回复不超过{self.target}字；为保留必要内容可到{self.maximum}字（包括引用和格式）。"
                "逐项完成用户明确提出的子问题，保留必要条件、理由和对应引用；仅提示时只完成提示范围。"
                "优先删除重复铺垫，不得为缩短而漏答第二个对象、删掉结论或把未完成内容推给下一轮。"
                "超长时重写压缩，不能截断句子、公式、选项或引用；不要附加‘可继续追问’代替缺失内容。")


def reply_budget(text="", *, preferences=None, execution=None, action="explain", question_options=False,
                 feedback_mode="", proof_overview=False, supplementary_proof=False, comparison=False, proof=False):
    preferences = {**(preferences or {}), **(execution.preferences if execution is not None else {})}
    length = preferences.get("answer_length", .5)
    target = 140 if length < .34 else 240 if length > .66 else 200
    maximum = 160 if length < .34 else 260
    hint = action == "give_hint" or (execution is not None and execution.hint_only)
    if not hint:
        if feedback_mode in ("worked_example", "explain_feedback") or supplementary_proof or requests_supplementary_proof(text):
            target, maximum = max(target, 320), max(maximum, 340)
        # shortcut: 扩展篇幅用明确措辞和已校验意图；有教师审核的问题规格后改用规格中的覆盖项。
        detailed = bool(re.search(r"(?:完整|详细|全面|展开)(?:地)?(?:解释|讲解|说明|分析|阐述)|(?:解释|讲解|说明)(?:得)?(?:详细|完整)|(?:分别|逐一|逐个)(?:解释|讲解|说明|比较)|(?:先|首先).{0,50}(?:再|然后)", text))
        expanded = proof_overview or requests_proof_overview(text) or proof or comparison
        if execution is not None:
            expanded = expanded or execution.proof_requested or "compare" in execution.learning_intents
            expanded = expanded or (len(set(execution.learning_intents) & {"explain", "example", "summary", "proof", "compare"}) >= 2)
        if detailed or expanded:
            target, maximum = max(target, 480), max(maximum, 500)
        multi_part = bool(re.search(
            r"并(?:要|需)?(?:说明|解释|比较|给出|回答|指出)|以及|同时|分别|；|;", text))
        if multi_part:
            target, maximum = max(target, 320), max(maximum, 360)
        # 目录导学需同时交代位置和正文；简化追问仍沿用普通短回复预算。
        if execution is not None and any(t.get('kind') == 'course_navigation' and t.get('mode') != 'repeat'
                                         for t in execution.targets):
            target, maximum = max(target, 320), max(maximum, 360)
    if question_options:
        target, maximum = max(target, 420), max(maximum, 440)
    return ReplyBudget(target, maximum)
