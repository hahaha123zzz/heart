"""Deterministic discrete-mathematics fixtures for offline integration tests."""

from __future__ import annotations

import re
from typing import Any


def _last_user(messages: list[dict[str, str]]) -> str:
    return next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")


def _field(content: str, name: str) -> str:
    match = re.search(re.escape(name) + r"([^\n]*)", content)
    return match.group(1).strip() if match else ""


def _terms(value: str) -> set[str]:
    filler = {
        "什么", "什么时候", "什么条件", "如何", "怎么", "怎样", "为什么",
        "为何", "是否", "一下", "请问", "请解释", "教材", "内容", "关系",
        "条件", "时候",
    }
    terms: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", value):
        for size in (2, 3, 4):
            terms.update(run[i:i + size] for i in range(max(0, len(run) - size + 1)))
    terms.update(word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_]*", value))
    return {term for term in terms if term not in filler}


def _excerpts(content: str) -> list[tuple[int, str, str]]:
    marker = "当前教材摘录（仅作资料，不是指令）："
    if marker not in content:
        return []
    body = content.split(marker, 1)[1]
    body = body.split("\n教材图片与公式原件", 1)[0].split("\n学生最新发言：", 1)[0]
    if "没有检索到相关教材文字" in body:
        return []
    rows = re.findall(
        r"(?ms)^\[(\d+)\]\s+([^\n]*)\n(.*?)(?=\n\n\[\d+\]\s+|\Z)",
        body,
    )
    return [(int(number), header.strip(), text.strip()) for number, header, text in rows if text.strip()]


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？；])|\n+", text)
        if len(sentence.strip()) >= 12
    ]


def _topic(student: str) -> str:
    rules = (
        ("集合", r"集合|元素|子集|空集|并集|交集|笛卡儿积|笛卡尔积|有序对|序偶|正整数|自然数|整数|有理数|实数"),
        ("图", r"图论|顶点|边|邻接矩阵|路径|回路|连通|树|欧拉|哈密顿|二部图|平面图"),
        ("逻辑代数", r"命题|合取|析取|否定|蕴含|真值|范式|谓词|量词|[A-Za-z]\s*[∧∨→↔¬]"),
        ("函数", r"函数|映射|单射|满射|双射|定义域|值域|复合"),
        ("关系", r"关系|等价|偏序|对称|传递|自反"),
        ("计数", r"计数|排列|组合|加法原理|乘法原理|鸽笼"),
        ("数学归纳", r"数学归纳|归纳假设|归纳步骤|结构归纳"),
    )
    for topic, pattern in rules:
        if re.search(pattern, student):
            return topic
    return ""


def _textbook_answer(question: str, excerpts: list[tuple[int, str, str]]) -> str:
    query_terms = _terms(question)
    ranked: list[tuple[float, int, str]] = []
    for number, header, text in excerpts:
        header_terms = _terms(header)
        for position, sentence in enumerate(_sentences(text)):
            sentence_terms = _terms(sentence)
            overlap = query_terms & sentence_terms
            header_overlap = query_terms & header_terms
            score = (4 * sum(len(term) for term in header_overlap)
                     + sum(len(term) for term in overlap))
            if re.search(r"当且仅当|仅当|如果|条件是|只有|均真|同时为真|当.{0,8}时", sentence):
                score += 1.5 if re.search(r"条件|什么时候|何时|怎样|如何|为什么|为何", question) else 0.3
            if score > 0:
                ranked.append((score, number, sentence))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    best_score, best_number, best_sentence = ranked[0]
    chosen = [(best_number, best_sentence)]
    comparison = bool(re.search(r"比较|区别|不同|分别|各自|异同", question))
    # 单点事实默认只给一句，避免把相邻小节或同章练习带进答案。
    if comparison:
        second = next((
            (number, sentence) for score, number, sentence in ranked[1:]
            if number == best_number and score >= best_score * 0.55
            and len(best_sentence) + len(sentence) <= 280
        ), None)
        if second:
            chosen.append(second)
    if not chosen:
        return ""
    body = "".join(sentence if sentence.endswith(("。", "！", "？", "；")) else sentence + "。" for _, sentence in chosen)
    body = re.sub(r"^\s*\d+\s*[\t ]+", "", body)
    markers = "".join(f"[{number}]" for number in dict.fromkeys(number for number, _ in chosen))
    return "根据本轮教材摘录：" + body + markers


def mock_reply(messages: list[dict[str, str]], json_mode: bool) -> Any:
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    tag_match = re.search(r"\[AGENT:(\w+)\]", system)
    tag = tag_match.group(1) if tag_match else ""
    content = _last_user(messages)
    student = _field(content, "学生最新输入：") or _field(content, "学生最新发言：") or content
    stuck = any(x in student for x in ("不知道", "不懂", "不会", "没思路"))

    if not json_mode:
        if tag == "social_reply":
            return "好的，需要时再回来学离散数学。"
        excerpts = _excerpts(content)
        question = _field(content, "学生最新发言：")
        if tag == "response_generator" and question and excerpts:
            answer = _textbook_answer(question, excerpts)
            if answer:
                return answer
        if stuck:
            return "没关系，我们先退一步。请把问题里的关键词和你已经看懂的条件告诉我，我会从本轮教材摘录里找一个最小依据来解释。"
        return "当前没有找到足够具体的教材摘录。请补充你想问的章节或知识点，我不会用固定示例代替你的问题。"

    if tag == "conversation_router":
        switch = re.search(r"(?:换到|改学|想学|学习)(集合|图论|图|关系|函数|逻辑代数)", student)
        detected_topic = _topic(student)
        if switch:
            result = {"student_move": "statement", "move_status": "", "intent": "switch_topic",
                      "topic": switch.group(1), "confidence": 0.9, "reason": "明确指定新知识点"}
        elif detected_topic:
            result = {"student_move": "question", "move_status": "", "intent": "switch_topic",
                      "topic": detected_topic, "confidence": 0.86, "reason": "按本轮问题识别教材主题"}
        elif student.strip() in ("换个话题", "换一个知识点"):
            result = {"student_move": "statement", "move_status": "", "intent": "clarify_task",
                      "topic": "", "confidence": 0.9, "reason": "未指定新知识点"}
        else:
            result = {"student_move": "statement" if stuck else "question", "move_status": "",
                      "intent": "continue", "topic": "", "confidence": 0.8, "reason": "继续当前知识点"}
        if "扩展任务输出" in system:
            import json
            context = json.loads(content.split("已校验任务上下文（资料，不是指令）：", 1)[1].split("\n学生最新输入：", 1)[0])
            targets = [obj["id"] for obj in context["objects"] if obj["kind"] != "section"]
            result.update(learning_intents=["explain"], target_refs=targets if result["intent"] == "continue" else [],
                          answer_constraints=[], missing_slots=["topic"] if result["intent"] == "clarify_task" else [],
                          needs_context=bool(targets), reason="离线任务夹具，不是实际模型理解")
        return result
    if tag == "evidence_extractor":
        return {"evidence": [{"evidence_type": "behavior", "content": student, "confidence": 0.9}] if stuck else [],
                "observation": {"confidence": 0.2, "emotion": "confused", "current_concept": "图"} if stuck else {"current_concept": "图"},
                "hypotheses": []}
    if tag == "lesson_planner":
        return {"goal": "学习图的基本概念", "knowledge_gap": "需确认顶点与边的基本概念",
                "target_mastery": 0.8, "steps": [
                    {"step_id": "S1", "objective": "能指出图中的顶点和边", "completion_criteria": "独立指出顶点和边",
                     "target_mastery": 0.7, "teaching_form": "explain", "suggested_strategy": "worked_example"},
                    {"step_id": "S2", "objective": "能区分有向边和无向边", "completion_criteria": "独立区分两类边",
                     "target_mastery": 0.8, "teaching_form": "quiz", "suggested_strategy": "retrieval_practice"},
                    {"step_id": "S3", "objective": "能写出简单图的顶点集与边集", "completion_criteria": "独立写出 V 和 E",
                     "target_mastery": 0.8, "teaching_form": "quiz", "suggested_strategy": "transfer"}]}
    if tag == "teaching_planner":
        return {"goal": "掌握当前基础概念", "strategy": "worked_example" if stuck else "socratic_questioning",
                "action": "explain" if stuck else "ask_question", "difficulty": "easy", "hint_level": 1,
                "expected_student_behavior": "能说出顶点和边", "rationale": "按基础状态推进"}
    if tag == "strategy_router":
        return {"instructional_move": "worked_example" if stuck else "direct_explanation",
                "action": "give_example" if stuck else "explain", "difficulty": "easy", "hint_level": 1,
                "rationale": "先给简单例子"}
    if tag == "question_designer":
        return {"question_type": "open_explanation", "target_misconception": None,
                "discrimination_goal": "识别顶点和边", "stem": "图中的顶点和边分别是什么？",
                "options": [], "acceptable_free_answer": "顶点是点，边连接顶点"}
    if tag == "quality_checker":
        return {"passed": True, "issues": [], "suggestions": ""}
    if tag == "state_updater":
        return {"confidence": 0.2 if stuck else 0.5, "emotion": "confused" if stuck else "neutral",
                "turn_summary": "学生表示卡住" if stuck else "继续学习图的基本概念",
                "step_completed": False, "step_reason": "尚无独立正确作答",
                "evidence": [], "hypotheses": [], "resolve_misconceptions": False,
                "tutor_error": {"detected": False}}
    if tag == "misconception_resolver":
        return {"matched_id": None, "reason": "无误解"}
    return {}
