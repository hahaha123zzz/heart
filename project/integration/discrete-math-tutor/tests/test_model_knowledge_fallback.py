"""教材不足时的模型知识兜底；原文引用和正式题目仍保持核验。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.agent_loop import LoopResult
from agents.agent_loop_service import _publish_gate, run_agent_loop_turn
from agents.q3_navigation import LearningTarget, StubLearningNavigator
from agents.q3_tools import RetrieveCourseTool
from agents.tool_protocol import ToolRegistry
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_q3_agent_loop import ScriptedLLM, final_round


class ModelKnowledgeFallbackTests(unittest.TestCase):
    def gate(self, *, fallback=True, sources=None):
        gate=_publish_gate(None,SimpleNamespace(message='解释预测编码'),LearningTarget('kp:test','预测编码'),
                           allow_model_knowledge=fallback)
        return gate,LoopResult(sources=sources or [])

    def test_no_textbook_source_allows_model_knowledge_without_citations(self):
        gate,result=self.gate()
        self.assertTrue(gate('预测编码用预测与实际输入的偏差来更新内部模型。',result)[0])

    def test_no_textbook_source_still_rejects_invented_citations(self):
        gate,result=self.gate()
        accepted,reason=gate('预测编码用预测误差更新模型。[1]',result)
        self.assertFalse(accepted)
        self.assertIn('没有教材引用来源',reason)

    def test_partial_sources_do_not_limit_general_explanation_to_the_excerpt(self):
        gate,result=self.gate(sources=[{'index':1,'text':'预测编码是一种认知理论。'}])
        with patch('knowledge.fixed_book.active',return_value=None):
            self.assertTrue(gate('可以把预测编码理解为不断根据误差修正预测的过程。',result)[0])
        self.assertEqual(result._publication['pdf_references'],[])

    def test_source_bound_task_still_requires_original_evidence(self):
        gate,result=self.gate(fallback=False)
        accepted,reason=gate('以下是我记忆中的教材原文。',result)
        self.assertFalse(accepted)
        self.assertIn('没有可核验的教材来源',reason)

    def test_source_bound_task_cannot_be_reopened_by_blended_teaching_state(self):
        gate=_publish_gate(None,SimpleNamespace(message='引用教材原文'),LearningTarget('kp:test','原文'),
                           teaching=SimpleNamespace(evidence_mode='blended'),allow_model_knowledge=False)
        self.assertFalse(gate('模型记忆不能作为本次教材原文。',LoopResult())[0])

    def run_turn(self,message,replies):
        llm=ScriptedLLM([final_round(text) for text in replies])
        navigator=StubLearningNavigator(target=LearningTarget('kp:test','实验心理学'),sources=[])
        registry=ToolRegistry();registry.register(RetrieveCourseTool())
        with (patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'0','Q5_LEARNING_ENABLED':'0'}),
              patch('agents.teaching_skills.enabled',return_value=False),
              patch('agents.selection_loop.enabled',return_value=False),
              patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())),
              patch('agents.agent_loop_service.build_registry',return_value=registry)):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=llm,memory=None),
                request=ChatRequest(student_id='isolated-fallback',message=message),
                context=TaskContext(student_id='isolated-fallback',message=message),navigator=navigator)
        return result,llm,navigator

    def test_ordinary_question_falls_back_after_one_empty_retrieval_without_teaching_state(self):
        reply='预测编码用预测误差修正内部模型。'
        result,llm,navigator=self.run_turn('什么是预测编码',[reply])
        self.assertEqual(result['answer_status'],'answered',result)
        self.assertEqual(result['reply'],reply)
        self.assertEqual(result['sources'],[])
        self.assertEqual(len([c for c in navigator.calls if 'search' in c]),1)
        self.assertEqual(llm.calls[0]['tools'],[])
        self.assertIn('模型自身知识',' '.join(str(m.get('content','')) for m in llm.calls[0]['messages']))

    def test_person_question_can_use_model_knowledge_without_fabricating_identity(self):
        reply='钟毅平从事心理学研究；对其当前单位和职务，我没有足够把握。'
        result,_,_=self.run_turn('钟毅平是谁',[reply])
        self.assertEqual(result['answer_status'],'answered',result)
        self.assertEqual(result['reply'],reply)

    def test_hallucinated_citation_is_removed_in_one_retry_without_repeated_search(self):
        result,llm,navigator=self.run_turn('什么是预测编码',[
            '预测编码用预测误差修正内部模型。[1]','预测编码用预测误差修正内部模型。'])
        self.assertEqual(result['answer_status'],'answered',result)
        self.assertNotIn('[1]',result['reply'])
        self.assertEqual(len(llm.calls),2)
        self.assertEqual(len([c for c in navigator.calls if 'search' in c]),1)

    def test_explicit_original_request_does_not_pass_as_model_knowledge(self):
        result,_,_=self.run_turn('引用教材原文解释预测编码',['我记得教材是这样说的。']*3)
        self.assertNotEqual(result['answer_status'],'answered')

    def test_only_reading_a_page_does_not_disable_general_knowledge(self):
        from agents.agent_loop_service import _allows_model_knowledge
        self.assertTrue(_allows_model_knowledge(ChatRequest(student_id='s',message='什么是预测编码')))
        for text in ['引用教材原文解释预测编码','原图5-1里有什么','第5页的原文是什么']:
            with self.subTest(text=text):
                self.assertFalse(_allows_model_knowledge(ChatRequest(student_id='s',message=text)))

    def test_mentioning_a_gap_in_the_textbook_does_not_disable_model_knowledge(self):
        from agents.agent_loop_service import _allows_model_knowledge
        text='教材里没有讲主动推断，请用你自己的知识解释一下。'
        self.assertTrue(_allows_model_knowledge(ChatRequest(student_id='s',message=text)))
        result,_,_=self.run_turn(text,['主动推断通过行动与知觉来更新预测。'])
        self.assertEqual(result['answer_status'],'answered',result.get('loop_error'))

    def test_shared_policy_permits_partial_coverage_and_person_questions(self):
        from agents.teaching_skills import ANSWER_CONTRACT, PRIORITY
        for policy in [ANSWER_CONTRACT,PRIORITY]:
            self.assertIn('模型自身知识',policy)
            self.assertIn('人物',policy)
            self.assertIn('部分',policy)
