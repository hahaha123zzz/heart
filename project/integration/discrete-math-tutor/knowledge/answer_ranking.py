"""Shared answer-sentence ranking for citation selection and offline generation."""

from __future__ import annotations

import re


INTRO_SENTENCE = re.compile(
    r"本章|本节|下面|介绍|回顾|学习内容|基本工具|这一小节|我们将|读者|"
    r"主要研究|将要讨论"
)
EXERCISE_SENTENCE = re.compile(r"练习|习题|模仿定理|作业|思考题")
ANSWER_CUES = {
    "object": re.compile(r"(?:组成)?对象|元素|其组成"),
    "condition": re.compile(r"当且仅当|仅当|如果|若|只有|当.{0,10}时|取真|为真|条件"),
    "contrast": re.compile(r"区别|不同|相反|分别|而|但|互|各自|比较"),
    "explain": re.compile(r"因为|由于|因此|从而|所以|说明|使得|为了|依据"),
    "formula": re.compile(r"公式|等式|表示为|记为|=|等于"),
    "proof": re.compile(r"假设|归纳|前提|推理规则|证明|推出|得证"),
    "definition": re.compile(r"称为|定义为|是指|称作|定义为|是.{0,12}概念"),
}


def terms(value: str) -> set[str]:
    filler = {
        "什么", "什么时候", "什么条件", "如何", "怎么", "怎样", "为什么",
        "为何", "是否", "一下", "请问", "请解释", "教材", "内容", "关系",
        "条件", "时候", "什么关系", "有何关系", "之间", "原来", "原命题",
    }
    result: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", value):
        for size in (2, 3, 4):
            result.update(run[i:i + size] for i in range(max(0, len(run) - size + 1)))
    result.update(word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_]*", value))
    return {term for term in result if term not in filler}


def question_kind(question: str) -> str:
    if re.search(r"证明|推理|归纳", question):
        return "proof"
    if re.search(r"为什么|为何|原因|如何|怎样", question):
        return "explain"
    if re.search(r"对象|元素是谁|组成对象", question):
        return "object"
    if re.search(r"什么时候|何时|条件|取真|为真", question):
        return "condition"
    if re.search(r"区别|不同|差别|比较|关系|异同", question):
        return "contrast"
    if re.search(r"公式|表达式|怎么算|多少", question):
        return "formula"
    if re.search(r"什么是|定义|是什么", question):
        return "definition"
    return "general"


def score_sentence(
    question: str,
    header: str,
    sentence: str,
    *,
    evidence_rank: int = 1,
) -> float:
    query_terms = terms(question)
    sentence_terms = terms(sentence)
    header_terms = terms(header)
    kind = question_kind(question)
    overlap = query_terms & sentence_terms
    header_overlap = query_terms & header_terms
    score = (
        1.5 * sum(len(term) for term in header_overlap)
        + 1.5 * sum(len(term) for term in overlap)
    )
    cue = ANSWER_CUES.get(kind)
    if cue and cue.search(sentence):
        score += 4
    if kind == "condition" and re.search(r"当且仅当|仅当|如果|若|只有|当.{0,10}时", sentence):
        score += 2
    if kind == "contrast":
        if re.search(r"(?:真|假).{0,24}(?:假|真)", sentence):
            score += 7
        else:
            score -= 4
    if kind == "object" and re.search(r"(?:组成)?对象是|其组成对象|元素是", sentence):
        score += 3
    if kind == "definition" and sentence.lstrip().startswith("定义"):
        score += 2
    if "邻接矩阵" in question and re.search(r"aij|a_ij|分量|重数|为0|为1", sentence):
        score += 6
    if "否定" in question and re.search(r"否定词|否定|┐|并非", sentence):
        score += 8
    if "否定" in question and re.search(
        r"p\s*真.{0,12}(?:p\s*)?假.{0,12}p\s*假.{0,12}(?:p\s*)?真",
        sentence,
    ):
        score += 12
    if re.search(r"合取|∧", question) and re.search(r"合取词|合取|p∧q|并且", sentence):
        score += 8
    if "析取" in question and re.search(r"析取词|析取|p∨q|或者", sentence):
        score += 8
    if "反对称" in question and re.search(
        r"称R是反对称|R反对称|xRy且yRx|xRy.{0,8}yRx", sentence
    ):
        score += 8
    if "反对称" in question and re.search(
        r"(?:称.{0,12}反对称|R\s*反对称).{0,40}(?:如果|当且仅当)",
        sentence,
    ):
        score += 10
    if "单射" in question and re.search(
        r"单射函数|称f为.{0,16}单射|x1.{0,8}x2.{0,24}f\(x1\).{0,12}f\(x2\)",
        sentence,
    ):
        score += 10
    if "绝对值" in question and "绝对值" in sentence:
        score += 8
    if re.search(r"函数.{0,4}复合|复合函数|f\s*[○∘]\s*g", question) and re.search(
        r"先|然后|依次|次序|次序相反|g\(f|f\(x|复合", sentence
    ):
        score += 8
    if re.search(r"证明.{0,8}演绎|演绎.{0,8}证明", question) and re.search(
        r"证明是演绎|演绎.{0,8}证明|空集.{0,8}特例|推理关系", sentence
    ):
        score += 7
    if "归纳假设" in question and re.search(r"归纳假设|假设P\(k\)真|假设P\(k＋", sentence):
        score += 40
    if "下一步" in question and re.search(r"推出|k＋l|k\+1|归纳过程", sentence):
        score += 4
    if re.search(r"有序对|\(a,b\)|\(b,a\)", question) and re.search(
        r"\(a,b\)|\(b,a\)|相等|相同|不同", sentence
    ):
        score += 5
    if re.search(r"有序对|序偶", question) and re.search(
        r"称.{0,12}有序对|有序对.{0,20}(?:由|是)|第一分量|第二分量|component",
        sentence,
    ):
        score += 12
    if "乘法原理" in question and re.search(r"相继|依次|分步|第一步|第二步|n1|n2", sentence):
        score += 5
    if INTRO_SENTENCE.search(sentence):
        score -= 6
    if EXERCISE_SENTENCE.search(sentence):
        score -= 6
    if sentence.count("[公式或对象]") >= 2:
        score -= 4
    if 18 <= len(sentence) <= 220:
        score += 0.6
    elif len(sentence) > 320:
        score -= 1.5
    score += max(0, 1.2 - 0.15 * evidence_rank)
    return score


def sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？；])|\n+", text)
        if len(sentence.strip()) >= 12
    ]


def rank_excerpt_sentences(
    question: str,
    excerpts: list[tuple[int, str, str]],
) -> list[tuple[float, int, str]]:
    ranked = [
        (
            score_sentence(question, header, sentence, evidence_rank=number),
            number,
            sentence,
        )
        for number, header, text in excerpts
        for sentence in sentences(text)
    ]
    return sorted(
        (item for item in ranked if item[0] > 0),
        key=lambda item: (item[0], -item[1]),
        reverse=True,
    )
