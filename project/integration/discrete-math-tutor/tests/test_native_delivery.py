"""原生能力交付边界：来源、题目与阅读指令必须进入正式保存结果。"""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.deeptutor.native_executor import NativeTurnExecutor, _public_result
from models.chat_request import ChatRequest


def quiz(success=True):
    return {'response':'答案是 B，稍后开始出题。','mode':'custom','summary':{'success':success,
        'requested':1,'completed':int(success),'failed':int(not success),'results':[{'qa_pair':{
            'question_id':'q1','question':'哪个变量由研究者操纵？','question_type':'choice',
            'options':{'A':'因变量','B':'自变量'},'correct_answer':'B','explanation':'私有解析'}}]}}


class NativeDeliveryTests(unittest.TestCase):
    def consume(self, *, capability='chat',state=None,documents=None,events=()):
        request=ChatRequest(student_id='audit',session_id='audit',request_id='r',message='解释变量',capability=capability)
        state=state or {'status':'completed','reply':'已经完成。','result':{},'sources':[]}
        backend=SimpleNamespace(native_events=lambda *a,**k:(event for event in [*events,{'type':'done','seq':99}]),native_status=lambda *a:state)
        saves=[]
        def save(**kwargs):saves.append(kwargs);return {},kwargs['result']
        executor=NativeTurnExecutor.__new__(NativeTurnExecutor)
        executor.backend=backend;executor.repo=SimpleNamespace(save=save)
        self.exchanges=[]
        def append(*a,**kwargs):
            if a[1]=='assistant':self.exchanges.append(kwargs)
            return 1
        executor.memory=SimpleNamespace(repo=SimpleNamespace(unit_of_work=nullcontext,append_conversation=append))
        executor.orchestrator=SimpleNamespace()
        task={'id':'task','student_id':'audit','session_id':'audit','revision':1,'epoch':0,'knowledge_point':'变量',
            'payload':request.model_dump(),'context':{'document_versions':documents or {}}}
        binding={'key':{},'receipt_id':'r','after_seq':0,'start':{'capability':capability}}
        with patch('integrations.deeptutor.task_projection.checked_task',return_value=task):
            result=executor._consume(request,task,binding,None,None,None)
        return result,saves
    def test_generated_question_structure_survives_but_answers_do_not(self):
        result=_public_result(quiz(),{'id':'task'},{'start':{'capability':'deep_question'}})
        self.assertIn('summary',result)
        qa=result['summary']['results'][0]['qa_pair']
        self.assertEqual(qa['question_id'],'q1')
        self.assertEqual(qa['options']['B'],'自变量')
        self.assertNotIn('correct_answer',qa);self.assertNotIn('explanation',qa)
        self.assertNotIn('答案是',result['response'])
    def test_auto_routed_quiz_uses_actual_capability_and_filters_answers(self):
        state={'status':'completed','capability':'deep_question','reply':'答案是B', 'result':quiz()}
        result,_=self.consume(capability='chat',state=state)
        self.assertEqual(result['capability'],'deep_question')
        question=result['native_result']['summary']['results'][0]['qa_pair']
        self.assertEqual(question['question_id'],'q1')
        self.assertNotIn('correct_answer',question)
        self.assertNotIn('explanation',question)
        self.assertNotIn('答案是',result['reply'])

    def test_mastery_projection_excludes_private_answers_and_tool_text(self):
        from integrations.deeptutor.native_delivery import public_mastery_events
        events=[{'type':'tool_result','content':'私有正文','metadata':{'tool_metadata':{
            'mastery_question':{'question_id':'q','prompt':'题干','expected_answer':'私有答案',
                'explanation':'私有解析','options':[{'label':'A','body':'选项','is_correct':True}]}}}}]
        projected=public_mastery_events(events)
        self.assertEqual(projected[0]['metadata']['tool_metadata']['mastery_question']['options'],[{'label':'A','body':'选项'}])
        self.assertNotIn('私有',str(projected))
        self.assertNotIn('is_correct',str(projected))

    def test_mastery_grade_preserves_native_nested_public_result(self):
        from integrations.deeptutor.native_delivery import public_mastery_events
        events=[{'type':'tool_result','metadata':{'tool_metadata':{'mastery_grade':{
            'private_state':'不公开','result':{'question_id':'q','is_correct':True,
                'learner_answer':'A','correct_label':'A','explanation':'判定说明','secret':'不公开'}}}}}]
        projected=public_mastery_events(events)
        grade=projected[0]['metadata']['tool_metadata']['mastery_grade']['result']
        self.assertEqual(grade['question_id'],'q')
        self.assertTrue(grade['is_correct'])
        self.assertNotIn('不公开',str(projected))

    def test_failed_quiz_is_not_published_as_answered(self):
        result,saves=self.consume(capability='deep_question',state={'status':'completed','reply':'现在开始。','result':quiz(False)})
        self.assertEqual(result['answer_status'],'incomplete_answer')
        self.assertEqual(saves[-1]['status'],'failed')
    def test_verified_native_sources_reach_publication_gate(self):
        source={'type':'heart_textbook_evidence','index':1,'source_id':'e1','document_id':'doc','version':'v1',
            'location':{'evidence':{'evidence_id':'e1','document_id':'doc','document_version':'v1'}},'text':'原文'}
        seen=[]
        def factory(*a,**k):
            def gate(text,outcome):
                seen.extend(outcome.sources);return False,'本测试只检查交接'
            return gate
        with patch('agents.agent_loop_service._publish_gate',side_effect=factory):
            self.consume(state={'status':'completed','reply':'原文[1]','result':{},'sources':[source]},documents={'doc':'v1'})
        self.assertEqual(seen,[source])
    def test_reader_instruction_is_saved_after_publication(self):
        state={'status':'completed','reply':'已定位。','result':{},'sources':[],
            'reader_actions':[{'document_id':'doc','version':'v1','page':2,'quote':''}]}
        with patch('knowledge.pdf_reader.document',return_value={'document_id':'doc','version':'v1','chapter_id':1,
            'page_count':3,'sections':[{'id':1,'page':1}]}):
            result,saves=self.consume(state=state,documents={'doc':'v1'})
        self.assertEqual(result['reader_actions'][0]['page'],2)
        self.assertEqual(result['reader_actions'][0]['task_id'],'task')
        self.assertEqual(result['reader_actions'][0]['status'],'requested')
        self.assertEqual(saves[-1]['result']['reader_actions'],result['reader_actions'])

    def test_publication_references_are_kept_for_history_reload(self):
        refs=[{'source_index':0,'selection_ref':{'document_id':'doc','version':'v1'}}]
        def factory(*args,**kwargs):
            def gate(text,outcome):
                outcome._publication={'reply':text,'pdf_references':refs,'textbook_sources':['教材']}
                return True,''
            return gate
        with patch('agents.agent_loop_service._publish_gate',side_effect=factory):
            result,_=self.consume()
        self.assertEqual(result['pdf_references'],refs)
        self.assertEqual(self.exchanges[0]['selection_ref']['pdf_references'],refs)
