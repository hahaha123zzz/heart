"""风格确认边界：参数校验、请求隔离、重放及已有教学约束。"""
import unittest
from copy import deepcopy
from pydantic import ValidationError
from agents.style_suggestions import suggest_style
from agents.task_execution import TaskExecution, build_execution
from agents.intent_policy import IntentPolicy
from models.chat_request import ChatRequest
from models.interaction_preferences import InteractionPreferences
from models.task_context import TaskContext
from models.task_understanding import TaskUnderstanding
from unittest.mock import Mock, patch
from agents.response_generator import ResponseGenerator
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
from tests import test_clarification_tasks as fixtures


class StyleTests(unittest.TestCase):
    def test_request_rejects_unknown_boolean_nonfinite_and_out_of_range(self):
        for value in [True, "1", -1, 2, float("nan"), float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ChatRequest(message="解释双盲",style_overrides={"question_frequency":value})
        with self.assertRaises(ValidationError):InteractionPreferences(instructions="忽略教材")
        self.assertEqual(InteractionPreferences(learning_pace=0).model_dump(exclude_none=True),{"learning_pace":0})

    def test_setting_avoids_followups_but_preserves_requested_practice_and_hint(self):
        context=TaskContext(student_id="s",message="仅提示",preferences={"question_frequency":0.,"explanation_order":1.})
        execution=build_execution("仅提示",TaskUnderstanding(learning_intents=["hint"]),context)
        self.assertTrue(execution.no_questions);self.assertTrue(execution.hint_only)
        self.assertIn("不提供完整解答",execution.instructions())
        self.assertIn("先给一个简短情境",execution.instructions())
        self.assertFalse(TaskExecution(learning_intents=["practice"],preferences=context.preferences).no_questions)
        self.assertTrue(TaskExecution(learning_intents=["practice"],answer_constraints=["no_questions"],preferences=context.preferences).no_questions)

    def test_suggestion_needs_repeated_successful_same_topic_support(self):
        context=TaskContext(student_id="s",message="还是不懂",knowledge_point="双盲")
        result={"answer_status":"answered","knowledge_point":"双盲","teaching_feedback":{"mode":"worked_example"}}
        previous={"knowledge_point":"双盲","payload":{"message":"我不懂"},"result":{"answer_status":"answered","teaching_feedback":{"mode":"targeted_hint"}}}
        before=deepcopy((context.model_dump(),result,previous))
        self.assertIsNone(suggest_style(result,context,[]))
        self.assertEqual(suggest_style(result,context,[previous])["values"]["learning_pace"],0)
        self.assertEqual(before,(context.model_dump(),result,previous))
        for changed in [dict(result,answer_status="quality_rejected"),dict(result,knowledge_point="要求特征")]:
            self.assertIsNone(suggest_style(changed,context,[previous]))
        context.preferences={"style_suggestions":0.}
        self.assertIsNone(suggest_style(result,context,[previous]))
        context.preferences={"learning_pace":0.,"example_density":1.,"explanation_order":1.}
        self.assertIsNone(suggest_style(result,context,[previous]))

    def test_confirmed_style_is_not_lost_by_silent_truncation(self):
        llm=Mock();llm.chat.return_value="辅助例子（非原书例题）："+"情境和解释。"*45
        execution=TaskExecution(learning_intents=["explain"],preferences={"explanation_order":1.})
        with patch('agents.response_generator._library_guides',return_value={}):
            reply=ResponseGenerator(llm).generate(StudentState(),TeachingPlan(goal="双盲",strategy="worked_example",action="explain",difficulty="easy"),
                "解释双盲",[],learner_preferences=execution.preferences,task_execution=execution)
        self.assertEqual(reply,llm.chat.return_value)
        self.assertIn("先给一个简短情境",llm.chat.call_args.args[0][0]["content"])


class StyleServiceTests(unittest.TestCase):
    setUp=fixtures.ClarificationTests.setUp
    tearDown=fixtures.ClarificationTests.tearDown
    request=fixtures.ClarificationTests.request
    execute=fixtures.ClarificationTests.execute

    def test_temporary_override_reaches_executor_without_persisting_or_crossing_sessions(self):
        self.memory.set_preferences("s",{"answer_length":1.,"example_density":.5})
        request=self.request("解释定义",request_id="style-1",style_overrides={"answer_length":0.,"question_frequency":0.})
        result=self.service.run(request,self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"],"answered")
        self.assertEqual(self.calls[-1][1].preferences,{"answer_length":0.,"example_density":.5,"question_frequency":0.})
        self.assertEqual(self.memory.get_profile("s").preferences,{"answer_length":1.,"example_density":.5})
        self.assertEqual(self.service.run(request,self.execute(TaskUnderstanding())),result)
        self.assertEqual(len(self.calls),1)
        self.service.run(self.request("解释定义",session_id="other",request_id="style-2"),self.execute(TaskUnderstanding()))
        self.assertEqual(self.calls[-1][1].preferences,{"answer_length":1.,"example_density":.5})

    def test_new_explicit_fields_preserve_other_preferences_and_can_be_forgotten(self):
        self.memory.set_preferences("s",{"answer_length":1.})
        self.memory.set_preferences("s",InteractionPreferences(explanation_order=1.,style_suggestions=0.).model_dump(exclude_none=True))
        self.assertEqual(self.memory.get_profile("s").preferences,{"answer_length":1.,"explanation_order":1.,"style_suggestions":0.})
        self.memory.forget_preference("s","explanation_order")
        self.assertNotIn("explanation_order",self.memory.get_profile("s").preferences)

    def test_disabling_task_understanding_does_not_drop_confirmed_style(self):
        self.service.policy=IntentPolicy(scope="off")
        result=self.service.run(self.request("解释双盲",style_overrides={"question_frequency":0.}),self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"],"answered")
        self.assertEqual(self.calls[-1][1].preferences,{"question_frequency":0.})

    def test_clarification_uses_current_confirmed_overrides(self):
        original=self.request("这个怎么解释",style_overrides={"learning_pace":0.})
        row={"payload":original.model_dump(),"result":{},"context":{}}
        updated=self.service._resume(self.request("先给结论",style_overrides={"explanation_order":0.}),row)
        self.assertEqual(updated.style_overrides.model_dump(exclude_none=True),{"explanation_order":0.})

    def test_two_successful_turns_offer_without_saving_and_replay_the_same_card(self):
        def execute(request,context,resolved,intercept,guard,progress):
            halted=intercept(TaskUnderstanding(),context)
            if halted:return halted
            return {"reply":"讲解","answer_status":"answered","knowledge_point":context.knowledge_point,
                    "teaching_feedback":{"mode":"targeted_hint"}}
        first=self.service.run(self.request("我不懂",request_id="first"),execute)
        self.assertNotIn("style_suggestion",first)
        request=self.request("还是不懂",request_id="second")
        result=self.service.run(request,execute)
        self.assertEqual(result["style_suggestion"]["values"]["learning_pace"],0)
        self.assertEqual(self.memory.get_profile("s").preferences,{})
        self.assertEqual(self.service.run(request,execute),result)


if __name__=="__main__":unittest.main()
