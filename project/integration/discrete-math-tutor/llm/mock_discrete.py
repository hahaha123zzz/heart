"""Deterministic discrete-mathematics fixtures for offline integration tests."""

from __future__ import annotations

import re
from typing import Any

from knowledge.answer_ranking import question_kind, rank_excerpt_sentences


def _last_user(messages: list[dict[str, str]]) -> str:
    return next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")


def _field(content: str, name: str) -> str:
    match = re.search(re.escape(name) + r"([^\n]*)", content)
    return match.group(1).strip() if match else ""


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


def _derived_answer(question: str, excerpts: list[tuple[int, str, str]]) -> str:
    """Answer questions that require combining a definition with an example."""
    compact_question = re.sub(r"\s+", "", question)
    compact_excerpts = [(number, re.sub(r"\s+", "", text)) for number, _, text in excerpts]

    def marker(*keywords: str) -> int | None:
        return next((
            number for number, text in compact_excerpts
            if any(keyword in text for keyword in keywords)
        ), None)

    ordered_pair = marker("第一分量", "第二分量", "序偶")
    if re.search(r"有序对|序偶", question) and re.search(r"相等|相同", question) and ordered_pair:
        return (
            "根据本轮教材摘录：有序对不一定相等。序偶相等要求两个分量分别相等，"
            f"所以(a,b)与(b,a)只有在a=b时才相等。[{ordered_pair}]"
        )

    negation = next((
        number for number, text in compact_excerpts
        if "否定" in text and ("p真时" in text or "┐p" in text)
    ), None)
    if "否定" in question and "真值" in question and negation:
        return (
            "根据本轮教材摘录：命题p的否定┐p与原命题的真值相反。"
            f"p真时┐p假，p假时┐p真。[{negation}]"
        )

    induction = marker("归纳假设")
    if "数学归纳" in question and "归纳假设" in question and induction:
        return (
            "根据本轮教材摘录：归纳假设是归纳步骤的前提；"
            f"先假定前一步成立，再利用它推出下一步也成立。[{induction}]"
        )

    individual_domain = marker("个体域")
    if "个体域" in question and re.search(r"变化|改变|真假", question) and individual_domain:
        return (
            "根据本轮教材摘录：会变化。同一个全称命题在不同个体域中可能有不同真假，"
            f"个体域改变会影响命题是否为真。[{individual_domain}]"
        )

    absolute = marker("绝对值函数", "绝对值")
    injection = marker("单射", "单值的")
    if "绝对值" in question and "单射" in question and absolute and injection:
        markers = "".join(f"[{number}]" for number in dict.fromkeys((absolute, injection)))
        return (
            "根据本轮教材摘录：这个映射不是单射。因为-1和1的绝对值都是1，"
            f"不同原像对应了同一个值，不满足单射要求。{markers}"
        )

    antisymmetry = next((
        number for number, text in compact_excerpts
        if "反对称" in text and ("xRy" in text or "aRb" in text)
    ), None)
    if "反对称" in question and antisymmetry:
        return (
            "根据本轮教材摘录：关系R具有反对称性，当且仅当对任意x和y，"
            f"若xRy且yRx，则x=y。[{antisymmetry}]"
        )

    multiplication = marker("乘法原理")
    pair = re.search(
        r"([一二三四五六七八九十两\d]+)种([\u4e00-\u9fff]{1,10}?)"
        r"(?:与|和|及|、)([一二三四五六七八九十两\d]+)种"
        r"([\u4e00-\u9fff]{1,10}?)(?=搭配|组合|选择|方案|，|。|？|$)",
        compact_question,
    )
    if "乘法原理" in question and multiplication and pair:
        numbers = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                   "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        first = int(pair.group(1)) if pair.group(1).isdigit() else numbers.get(pair.group(1))
        second = int(pair.group(3)) if pair.group(3).isdigit() else numbers.get(pair.group(3))
        if first is not None and second is not None:
            return (
                f"根据本轮教材摘录：先选{pair.group(2)}，有{first}种；"
                f"再选{pair.group(4)}，有{second}种。这是分步选择，"
                f"根据乘法原理，总数是{first}×{second}={first * second}种。[{multiplication}]"
            )

    adjacency = marker("aij", "邻接矩阵")
    if "邻接矩阵" in question and re.search(r"有边|相邻|两个顶点", question) and adjacency:
        return (
            "根据本轮教材摘录：查看邻接矩阵中表示vi到vj的元素aij。"
            "无重边时，aij为1表示vi到vj有边，aij为0表示无边；"
            f"有重边或权值时，aij表示边数或权值。[{adjacency}]"
        )

    composition = marker("次序刚好", "次序相反", "g(f(x))", "合成函数")
    if re.search(r"函数.{0,4}复合|复合函数|f[○∘]g", question) and composition:
        return (
            "根据本轮教材摘录：合成函数g○f先应用内层函数f，再应用外层函数g，"
            f"即(g○f)(x)=g(f(x))。[{composition}]"
        )
    return ""


def _textbook_answer(question: str, excerpts: list[tuple[int, str, str]]) -> str:
    derived = _derived_answer(question, excerpts)
    if derived:
        return derived
    kind = question_kind(question)
    ranked = rank_excerpt_sentences(question, excerpts)
    if not ranked:
        return ""
    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    best_score, best_number, best_sentence = ranked[0]
    chosen = [(best_number, best_sentence)]
    comparison = kind in {"contrast", "explain", "proof"}
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
