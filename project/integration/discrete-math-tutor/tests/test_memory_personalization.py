"""跨会话教学记忆验收：文件 SQLite、真实生成器/规划器，记录模拟模型输入。"""
import unittest
from unittest.mock import patch
from agents.response_generator import ResponseGenerator
from agents.teaching_planner import TeachingPlanner
from agents.teaching_policy import select_policy
from agents.evidence_extractor import MisconceptionHypothesis
from database.database import session_scope
from database.models import ExerciseSubmissionRow, EventEvidenceRow
from sqlalchemy import select
from memory.memory_manager import MemoryManager
from tests import test_memory_jobs as fixtures


class RecordingLLM:
    def __init__(self):
        self.messages=[]
        self.plans=[]

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        return "集合的交集包含两个集合共同的元素。"*24

    def chat_json(self, messages, **kwargs):
        self.plans.append(messages)
        return {}  # 触发真实 TeachingPolicy 的确定性回退。


class MemoryPersonalizationTests(unittest.TestCase):
    setUp=fixtures.MemoryJobTests.setUp
    tearDown=fixtures.MemoryJobTests.tearDown
    args=fixtures.MemoryJobTests.args
    make_tutor=fixtures.MemoryJobTests.make_tutor
    turn=fixtures.MemoryJobTests.turn

    def fresh_turn(self):
        self.memory=MemoryManager()  # 模拟新会话，不复用上一会话的缓存。
        tutor=self.make_tutor("question")
        llm=RecordingLLM()
        tutor.response_generator=ResponseGenerator(llm)
        tutor.teaching_planner=TeachingPlanner(llm)
        tutor.question_designer.design.return_value=None
        with patch("memory.retrieval._model",return_value=(None,None)):
            result=self.turn(tutor)
        return result,llm

    def test_saved_preferences_change_actual_generation_after_new_session(self):
        self.memory.set_preferences("s",{"answer_length":0,"example_density":1,"learning_pace":0})
        short,llm=self.fresh_turn()
        system=llm.messages[-1][0]["content"]
        self.assertIn("回复不超过140字",system)
        self.assertIn("多给一个具体小例子",system)
        self.assertIn("放慢节奏",system)
        self.memory.set_preferences("s",{"answer_length":1,"example_density":0,"learning_pace":1})
        long,other=self.fresh_turn()
        system=other.messages[-1][0]["content"]
        self.assertIn("回复不超过240字",system)
        self.assertIn("例子只在必要时使用",system)
        self.assertIn("更快进入小检查",system)
        self.assertLess(len(short["reply"]),len(long["reply"]))

    def test_cleared_preference_restores_default_next_session(self):
        self.memory.set_preferences("s",{"answer_length":0})
        self.memory.forget_preference("s","answer_length")
        _,llm=self.fresh_turn()
        self.assertIn("回复不超过200字",llm.messages[-1][0]["content"])
        self.assertNotIn("answer_length",self.memory.get_profile("s").preferences)

    def test_disputed_misconception_does_not_drive_next_teaching_policy(self):
        args=self.args()
        args["hypotheses"]=[(MisconceptionHypothesis(type="set_element_confusion",description="混淆元素与集合",source_quote=args["message"],confidence=.9),None)]
        self.memory.commit_learning_turn(**args)
        self.assertTrue(MemoryManager().get_state("s",self.point).has_misconception)
        target=self.memory.get_misconceptions("s",self.point)[0]
        mastery=self.memory.get_state("s",self.point).mastery
        self.memory.dispute_misconception("s",target.id,"我能区分元素和集合，请撤销这个判断")
        self.memory=MemoryManager()
        state=self.memory.get_state("s",self.point)
        self.assertFalse(state.has_misconception)
        self.assertEqual(state.mastery,mastery)
        self.assertNotIn("error_based_learning",select_policy(state)["recommended_strategies"])
        _,llm=self.fresh_turn()
        plan_input=llm.plans[-1][-1]["content"]
        self.assertNotIn("学生存在迷思概念",plan_input)
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="集合元素")
        self.assertEqual(context["learning_states"][0]["misconceptions"],[])
        self.assertTrue(any(i["evidence_type"]=="user_correction" for i in context["items"]))

    def test_long_history_and_other_student_scope_reach_actual_prompt(self):
        marker="我偏爱用苹果集合说明集合元素，跨会话标记甲"
        self.memory.append_exchange("s",marker,"旧助教示例",{"section_title":self.point})
        for i in range(25):self.memory.append("s","user",f"无关记录{i}")
        self.memory.ensure_student("other")
        self.memory.append("other","user","集合元素私密标记乙")
        self.assertNotIn(marker,str(self.memory.get_history("s")))
        _,llm=self.fresh_turn()
        prompt=llm.messages[-1][-1]["content"]
        self.assertIn(marker,prompt)
        self.assertNotIn("私密标记乙",prompt)
        self.assertIn("当前明确请求优先于历史偏好",llm.messages[-1][0]["content"])

    def submission(self, sid, method, assisted=False):
        output={"parts":[{"part_id":"a","confirmed":True,"method":method,"score":100,"feedback":"集合元素判断正确"}]}
        answers={"a":"集合元素1"}
        with session_scope() as session:
            session.add(ExerciseSubmissionRow(id=sid,student_id="s",request_id=sid,question_id="q1",version="v1",answers=answers,status="completed",result=output))
        self.memory.record_exercise_submission("s",self.point,sid,"q1","v1",answers,output,assisted)
        self.memory=MemoryManager()
        with patch("memory.retrieval._model",return_value=(None,None)):
            return self.memory.retrieve_context("s",title=self.point,question="集合元素")

    def test_independent_rule_exercise_preserves_source_in_next_prompt(self):
        context=self.submission("rule-sub","rule")
        items=[i for i in context["items"] if i["source"]["kind"]=="exercise"]
        self.assertTrue(items)
        self.assertEqual(items[0]["verification"],"rule_verified")
        self.assertTrue(items[0]["independent"])
        self.assertEqual(items[0]["source"]["question_id"],"q1")
        self.assertEqual(items[0]["source"]["version"],"v1")
        mastery=self.memory.get_state("s",self.point).mastery
        _,llm=self.fresh_turn()
        self.assertIn("rule-sub",llm.messages[-1][-1]["content"])
        self.assertEqual(self.memory.get_state("s",self.point).mastery,mastery)

    def test_ai_or_unknown_grading_never_becomes_rule_verified(self):
        for method in ("ai_assisted","unknown"):
            with self.subTest(method=method):
                context=self.submission("sub-"+method,method)
                items=[i for i in context["items"] if i["source"]["id"]=="sub-"+method]
                self.assertTrue(items)
                self.assertTrue(all(i["verification"]=="ai_provisional" for i in items))
                evidence=self.memory.list_evidence("s",self.point)
                event_id=self.memory.repo.get_event("s","submission:sub-"+method)["id"]
                related=[i for i in evidence if i["event_id"]==event_id]
                self.assertTrue(related)
                self.assertTrue(all(i["verification"]=="ai_provisional" for i in related))

    def test_old_incorrect_verification_is_downgraded_on_index_rebuild(self):
        self.submission("old-ai","ai_assisted",assisted=True)
        event_id=self.memory.repo.get_event("s","submission:old-ai")["id"]
        with session_scope() as session:
            row=session.scalar(select(EventEvidenceRow).where(EventEvidenceRow.event_id==event_id))
            row.verification="rule_verified";row.independent=True
        self.memory=MemoryManager()
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="集合元素")
        items=[i for i in context["items"] if i["source"]["event_id"]==event_id]
        self.assertTrue(items)
        self.assertTrue(all(i["verification"]=="ai_provisional" for i in items))
        self.assertTrue(all(not i["independent"] for i in items))
        # 重建派生索引，不重写原始审计记录。
        with session_scope() as session:
            row=session.scalar(select(EventEvidenceRow).where(EventEvidenceRow.event_id==event_id))
            self.assertEqual(row.verification,"rule_verified")

    def test_assisted_exercise_is_not_independent(self):
        context=self.submission("hint-sub","rule",assisted=True)
        item=next(i for i in context["items"] if i["source"]["id"]=="hint-sub")
        self.assertFalse(item["independent"])


if __name__=="__main__":unittest.main()
