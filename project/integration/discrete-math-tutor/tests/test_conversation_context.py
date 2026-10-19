"""Q1-A/Q1-B：预算化历史、提示词块与连续追问契约。"""
import unittest
from unittest.mock import Mock

from agents.conversation_context import build_history, estimate_tokens
from agents.followup_context import followup_directive
from agents.prompt_blocks import PromptBlock, render_blocks
from agents.task_context_builder import TaskContextBuilder
from models.task_context import TaskContext


def exchange(index):
    return [
        {"role": "user", "content": "第%d轮问题：请解释概念%d" % (index, index)},
        {"role": "assistant", "content": "第%d轮解释：概念%d指教材中的定义。" % (index, index) * 3},
    ]


def history(count):
    rows = []
    for index in range(1, count + 1):
        rows.extend(exchange(index))
    return rows


class ConversationContextTests(unittest.TestCase):
    def test_budget_keeps_whole_turns_and_summarizes_older_ones(self):
        rows = history(8)
        result = build_history(rows, budget_tokens=60)
        self.assertLess(len(result.history), len(rows))
        self.assertEqual(len(result.history) % 2, 0)
        self.assertTrue(result.summary)
        self.assertIn("第1轮问题", result.summary)
        self.assertIn("对话摘要", result.summary)
        self.assertGreater(result.dropped_messages, 0)
        for index in range(0, len(result.history), 2):
            self.assertEqual(result.history[index]["role"], "user")
            self.assertEqual(result.history[index + 1]["role"], "assistant")

    def test_latest_turn_is_kept_even_when_it_exceeds_budget(self):
        rows = [{"role": "user", "content": "很长的问题" * 200},
                {"role": "assistant", "content": "很长的回答" * 200}]
        result = build_history(rows, budget_tokens=1)
        self.assertEqual(result.history, rows)
        self.assertEqual(result.summary, "")

    def test_legacy_rows_without_pairs_are_preserved_in_order(self):
        rows = [{"role": "user", "content": "一"}, {"role": "user", "content": "二"},
                {"role": "assistant", "content": "答"}]
        result = build_history(rows, budget_tokens=1000)
        self.assertEqual(result.history, rows)

    def test_estimate_tokens_has_a_real_fallback(self):
        self.assertGreater(estimate_tokens("任意文本" * 10), 0)
        self.assertGreater(estimate_tokens("plain text"), 0)

    def test_task_context_can_hold_more_than_four_turns(self):
        rows = history(6)
        context = TaskContext(student_id="s", message="继续", history=rows,
                              history_summary="更早的对话摘要")
        self.assertEqual(len(context.history), 12)
        self.assertEqual(context.history_summary, "更早的对话摘要")
        self.assertIn("history_summary", context.prompt_payload())

    def test_builder_applies_token_budget_instead_of_fixed_four(self):
        rows = history(10)
        built = TaskContextBuilder().build(
            student_id="s", message="继续解释", history=rows, history_budget_tokens=50)
        self.assertLess(len(built.history), len(rows))
        self.assertTrue(built.history_summary)
        self.assertLessEqual(len(built.history), 20)

    def test_render_blocks_keeps_named_sections_and_language(self):
        rendered = render_blocks([
            PromptBlock("general", " 基础规则 "),
            PromptBlock("empty", "   "),
            PromptBlock("history", "对话摘要"),
        ], language="zh")
        self.assertIn("## general", rendered)
        self.assertIn("基础规则", rendered)
        self.assertIn("## history", rendered)
        self.assertNotIn("## empty", rendered)
        self.assertIn("中文", rendered)


class FollowupDirectiveTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"role": "user", "content": "请解释自变量和被试间设计。"},
            {"role": "assistant", "content": "自变量是研究者操纵的变量。被试间设计中每名被试只接受一个水平。最后：请判断这个说法。"},
        ]

    def test_simplify_refers_to_previous_explanation_not_trailing_question(self):
        text = followup_directive("没听懂，请换一种更简单的说法。", self.rows)
        self.assertIn("上一轮助教解释", text)
        self.assertIn("不是末尾检查题", text)
        self.assertIn("自变量", text)

    def test_continue_comparison_keeps_previous_objects(self):
        text = followup_directive("继续比较，只确认被试内设计这一点。", self.rows)
        self.assertIn("明确缩小范围", text)
        self.assertIn("不重复", text)
        self.assertIn("请解释自变量和被试间设计", text)

    def test_accuracy_requirement_is_not_a_hint(self):
        text = followup_directive("请完整解释，不要编造实验数据。", self.rows)
        self.assertIn("准确性要求", text)
        self.assertIn("不是仅提示", text)

    def test_explicit_depth_change_invalidates_previous_hint_only(self):
        text = followup_directive("现在请完整解释刚才的问题，不用再出题。", self.rows)
        self.assertIn("明确改变", text)
        self.assertIn("上一轮仅提示约束失效", text)

    def test_no_followup_directive_for_new_self_contained_question(self):
        self.assertEqual(followup_directive("什么是随机分配？", self.rows), "")


    def test_router_receives_followup_target_and_scope_rules(self):
        from agents.conversation_router import ConversationRouter
        task = dict(student_move="question", move_status="", intent="continue", topic="",
                    confidence=.9, reason="追问", needs_context=True, learning_intents=["explain"],
                    target_refs=[], answer_constraints=[], missing_slots=[])
        llm = Mock()
        llm.chat_json.return_value = task
        built = TaskContext(student_id="s", message="没听懂，请换一种更简单的说法。",
                            knowledge_point="实验设计", history=self.rows)
        ConversationRouter(llm).route(built.message, built.knowledge_point, self.rows, [],
                                      context=built)
        messages = llm.chat_json.call_args.args[0]
        self.assertIn("上一轮助教解释", messages[1]["content"])
        self.assertIn("不是末尾检查题", messages[0]["content"])
        self.assertIn("上一轮仅提示约束失效", messages[0]["content"])


class ExplicitDepthTests(unittest.TestCase):
    def test_explicit_hint_request_creates_hint_scope_without_new_question(self):
        from types import SimpleNamespace
        from agents.task_execution import build_execution

        routing = SimpleNamespace(target_refs=[], answer_constraints=[], learning_intents=[])
        execution = build_execution("随机分配为什么有助于控制无关变量？只给一个提示。", routing)
        self.assertIn("hint", execution.learning_intents)
        self.assertTrue(execution.hint_only)
        self.assertTrue(execution.no_questions)
        self.assertTrue(execution.public()["hint_only"])
        self.assertIn("不出新题", execution.instructions())

    def test_explicit_full_explanation_replaces_previous_hint_scope(self):
        from types import SimpleNamespace
        from agents.task_execution import build_execution

        routing = SimpleNamespace(target_refs=[], answer_constraints=[], learning_intents=[])
        execution = build_execution("现在请完整解释刚才的问题，不用再出题。", routing)
        self.assertIn("explain", execution.learning_intents)
        self.assertFalse(execution.hint_only)
        self.assertTrue(execution.no_questions)
        self.assertNotIn("仅给一个知识点", execution.instructions())


    def test_simplify_followup_keeps_explain_without_becoming_hint(self):
        from types import SimpleNamespace
        from agents.task_execution import build_execution

        routing = SimpleNamespace(target_refs=[], answer_constraints=[], learning_intents=[])
        execution = build_execution("没听懂，请换一种更简单的说法。", routing)
        self.assertIn("explain", execution.learning_intents)
        self.assertFalse(execution.hint_only)

    def test_compare_followup_keeps_compare_intent(self):
        from types import SimpleNamespace
        from agents.task_execution import build_execution

        routing = SimpleNamespace(target_refs=[], answer_constraints=[], learning_intents=[])
        execution = build_execution("继续比较，只确认被试内设计这一点，不要引入其他设计。", routing)
        self.assertNotIn("compare", execution.learning_intents)
        self.assertIn("explain", execution.learning_intents)
        self.assertFalse(execution.hint_only)

    def test_narrowed_scope_is_explicit_and_does_not_keep_other_object(self):
        rows = [{"role": "user", "content": "请比较被试间设计和被试内设计。"},
                {"role": "assistant", "content": "被试间设计每名被试只接受一个水平；被试内设计接受全部水平。"}]
        text = followup_directive("只确认被试内设计这一点，不要引入其他设计。", rows)
        self.assertIn("明确缩小范围", text)
        self.assertIn("不重复", text)
        self.assertIn("被试内设计", text)

    def test_router_narrowed_scope_drops_compare_intent(self):
        from agents.conversation_router import ConversationRouter
        task = dict(student_move="question", move_status="", intent="continue", topic="",
                    confidence=.9, reason="追问", needs_context=True,
                    learning_intents=["compare"], answer_constraints=[],
                    target_refs=[], missing_slots=[])
        llm = Mock()
        llm.chat_json.return_value = task
        rows = [{"role": "user", "content": "请比较被试间设计和被试内设计。"},
                {"role": "assistant", "content": "被试间设计每名被试只接受一个水平；被试内设计接受全部水平。"}]
        built = TaskContext(student_id="s", message="只确认被试内设计这一点，不要引入其他设计。",
                            knowledge_point="实验设计", history=rows)
        result = ConversationRouter(llm).route(built.message, built.knowledge_point, rows, [],
                                               context=built)
        self.assertNotIn("compare", result.learning_intents)
        self.assertIn("explain", result.learning_intents)


    def test_router_overrides_simplify_statement_to_explanation_followup(self):
        from agents.conversation_router import ConversationRouter
        task = dict(student_move="statement", move_status="", intent="continue", topic="",
                    confidence=.9, reason="追问", needs_context=False, learning_intents=[],
                    target_refs=[], answer_constraints=[], missing_slots=[])
        llm = Mock()
        llm.chat_json.return_value = task
        built = TaskContext(student_id="s", message="没听懂，请换一种更简单的说法。",
                            knowledge_point="实验设计",
                            history=[{"role": "user", "content": "请解释自变量。"},
                                     {"role": "assistant", "content": "自变量是研究者操纵的变量。"}])
        result = ConversationRouter(llm).route(built.message, built.knowledge_point, built.history, [],
                                               context=built)
        self.assertEqual(result.student_move, "question")
        self.assertIn("explain", result.learning_intents)
        self.assertTrue(result.needs_context)

    def test_router_overrides_explicit_full_explanation(self):
        from agents.conversation_router import ConversationRouter
        task = dict(student_move="statement", move_status="", intent="continue", topic="",
                    confidence=.9, reason="追问", needs_context=False,
                    learning_intents=["hint"], answer_constraints=["hint_only"],
                    target_refs=[], missing_slots=[])
        llm = Mock()
        llm.chat_json.return_value = task
        built = TaskContext(student_id="s", message="现在请完整解释刚才的问题，不用再出题。",
                            knowledge_point="实验设计",
                            history=[{"role": "user", "content": "请解释自变量。"},
                                     {"role": "assistant", "content": "自变量是研究者操纵的变量。"}])
        result = ConversationRouter(llm).route(built.message, built.knowledge_point, built.history, [],
                                               context=built)
        self.assertEqual(result.student_move, "question")
        self.assertIn("explain", result.learning_intents)
        self.assertNotIn("hint", result.learning_intents)
        self.assertNotIn("hint_only", result.answer_constraints)
        self.assertIn("no_questions", result.answer_constraints)


    def test_hint_request_with_adjective_and_negated_full_explanation(self):
        from types import SimpleNamespace
        from agents.task_execution import build_execution

        routing = SimpleNamespace(target_refs=[], answer_constraints=[], learning_intents=[])
        execution = build_execution(
            "随机分配如何帮助控制无关变量？只给一个简短提示，不给完整解释或新的练习题。", routing)
        self.assertIn("hint", execution.learning_intents)
        self.assertNotIn("explain", execution.learning_intents)
        self.assertTrue(execution.hint_only)
        self.assertTrue(execution.no_questions)

    def test_generator_hint_forbids_mechanism_conclusion(self):
        from agents.response_generator import ResponseGenerator
        from agents.task_execution import TaskExecution
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState

        llm = Mock()
        llm.chat.return_value = "提示"
        plan = TeachingPlan(goal="随机分配", strategy="progressive_hinting",
                            action="give_hint", difficulty="easy")
        execution = TaskExecution(learning_intents=["hint"],
                                  answer_constraints=["hint_only", "no_full_answer", "no_questions"])
        ResponseGenerator(llm).generate(StudentState(), plan, "只给一个简短提示", [],
                                        task_execution=execution)
        system = llm.chat.call_args.args[0][0]["content"]
        self.assertIn("不得给出机制结论", system)
        self.assertIn("不得给出完整因果链", system)


    def test_quality_checker_simplify_followup_targets_previous_explanation(self):
        from agents.quality_checker import QualityChecker
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState

        llm = Mock()
        llm.chat_json.return_value = {"passed": True, "issues": []}
        plan = TeachingPlan(goal="简化上一轮解释", strategy="worked_example",
                            action="explain", difficulty="easy")
        QualityChecker(llm).check(
            "自变量就是研究者主动改变的条件。", StudentState(), plan,
            "没听懂，请换一种更简单的说法。",
            context={"followup_simplify": True, "followup_target": "自变量是研究者操纵的变量。"},
            textbook_excerpts="[1] 自变量是研究者操纵的变量。",
        )
        prompt = llm.chat_json.call_args.args[0][1]["content"]
        self.assertIn("不是当前阅读章节", prompt)
        self.assertIn("自变量是研究者操纵的变量", prompt)


class ResponseGeneratorContextTests(unittest.TestCase):
    def test_generator_receives_summary_and_all_budgeted_messages(self):
        from agents.response_generator import ResponseGenerator
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState

        llm = Mock()
        llm.chat.return_value = "回答 [1]"
        generator = ResponseGenerator(llm)
        rows = history(8)
        generator.generate(
            StudentState(student_id="s"),
            TeachingPlan(goal="解释", strategy="worked_example", action="explain", difficulty="easy"),
            "继续解释",
            rows,
            textbook_excerpts="教材原文｜证据ID:e1",
            history_summary="更早的对话：用户问过自变量。",
        )
        messages = llm.chat.call_args.args[0]
        system = messages[0]["content"]
        self.assertIn("[对话摘要]", system)
        self.assertIn("更早的对话", system)
        user_messages = [message["content"] for message in messages if message["role"] == "user"]
        self.assertTrue(any("第1轮问题" in text for text in user_messages))
        self.assertTrue(any("第8轮问题" in text for text in user_messages))


if __name__ == "__main__":
    unittest.main()
