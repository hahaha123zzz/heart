"""第五层契约、局部修复和真实循环边界；模型为可控替身。"""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock
from pydantic import ValidationError
from agents.response_composition import ResponseComposer, plan_response
from agents.agent_loop import LocalAgentLoop
from models.learning_response import BlockSpec, ResponsePlan
from tests.test_q3_agent_loop import ScriptedLLM, final_round, request
from agents.tool_protocol import ToolRegistry, Cancellation
from llm.client import LLMError
from llm.answer_events import AnswerEvents, current_answer


SOURCES = [{'source_id':'s1','document_id':'book','version':'v1','index':2,
            'text':'研究者主动改变的变量是自变量。','location':{}},
           {'source_id':'s2','document_id':'book','version':'v1','index':4,
            'text':'因变量是研究者观察测量的反应。','location':{}}]


def block(id, text='研究者主动改变的变量是自变量。', ids=None, provenance='paraphrase'):
    return {'block_id':id,'claims':[{'text':text,'source_ids':ids or ['s1'],'provenance':provenance}]}


def response(*blocks):
    return json.dumps({'blocks':list(blocks)},ensure_ascii=False)


class CompositionTests(unittest.TestCase):
    def test_inline_media_must_belong_to_the_claim_sources(self):
        sources = deepcopy(SOURCES)
        sources[0]['image_refs'] = [{'id': 'image-05-0004'}]
        text = '实验流程如下。\n\n![图5-2](media:image-05-0004)'
        composer = ResponseComposer(plan_response(target_id='t'))
        self.assertIn('(media:image-05-0004)', composer.accept(response(block('b1', text=text)), sources))
        for invalid, ids in (
            ('说明。![图片](media:unknown)', ['s1']),
            (text, ['s2']),
            ('说明。![图片](https://example.com/image.png)', ['s1']),
            ('说明。[链接](https://example.com)', ['s1']),
            ('说明。![<script>alert(1)</script>](media:image-05-0004)', ['s1']),
            ('![图5-2](media:image-05-0004)', ['s1']),
        ):
            with self.subTest(text=invalid):
                with self.assertRaises(ValueError):
                    ResponseComposer(plan_response(target_id='t')).accept(
                        response(block('b1', text=invalid, ids=ids)), sources)

    def test_composer_instructions_have_no_budget(self):
        composer = ResponseComposer(plan_response(target_id="kp:x", strategy="direct"))
        self.assertNotIn("字数预算", composer.instructions())

    def test_plan_consumes_strategy_and_constraints_without_model(self):
        self.assertEqual([b.semantic_type for b in plan_response(target_id='t',strategy='contrast').blocks],
                         ['direct_answer','comparison'])
        self.assertEqual([b.semantic_type for b in plan_response(target_id='t',strategy='worked_example',hint_only=True).blocks],['hint'])
        self.assertEqual(plan_response(target_id='t').plan_id,plan_response(target_id='t').plan_id)

    def test_dependencies_reject_cycles_forward_unknown_and_duplicate_ids(self):
        for specs in ([BlockSpec(block_id='a',semantic_type='explanation',depends_on=['a'])],
                      [BlockSpec(block_id='a',semantic_type='explanation'),BlockSpec(block_id='a',semantic_type='recap')]):
            with self.assertRaises(ValidationError):
                ResponsePlan(plan_id='p',target_id='t',strategy='x',blocks=specs)

    def test_claim_sources_quotes_and_markup_are_validated(self):
        for candidate in (block('b1',ids=['missing']),block('b1',text='原书没有这句话',provenance='quotation'),
                          block('b1',text='<script>run()</script>'),block('b1',text='伪造[99]'),
                          dict(block('b1'),expected_answer='private')):
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):
                ResponseComposer(plan_response(target_id='t')).accept(response(candidate),SOURCES)
        composer=ResponseComposer(plan_response(target_id='t'))
        self.assertIn('[2]',composer.accept(response(block('b1',provenance='quotation')),SOURCES))
        normalized=ResponseComposer(plan_response(target_id='t'))
        text=normalized.accept(response(block('b1',text='原有编号兼容[2]')),SOURCES)
        self.assertEqual(text,'原有编号兼容[2]')
        math=ResponseComposer(plan_response(target_id='t'))
        self.assertIn('p<0.05',math.accept(response(block('b1',text='p<0.05，效应量>0.2')),SOURCES))

    def test_invalid_dependency_discards_downstream_and_local_repair_preserves_good_block(self):
        composer=ResponseComposer(plan_response(target_id='t',strategy='contrast'))
        with self.assertRaises(ValueError):
            composer.accept(response(block('b1'),block('b2',ids=['invalid'])),SOURCES)
        self.assertEqual(composer.pending,['b2']);self.assertEqual(list(composer.accepted),['b1'])
        text=composer.accept(response(block('b2',text='两者分别是操纵与测量。',ids=['s1','s2'])),SOURCES)
        self.assertIn('[2][4]',text)
        other=ResponseComposer(composer.plan)
        with self.assertRaises(ValueError):other.accept(response(block('b1',ids=['bad']),block('b2')),SOURCES)
        self.assertEqual(other.pending,['b1','b2']);self.assertFalse(other.accepted)

    def test_optional_failure_is_partial_and_generated_example_is_labelled(self):
        plan=plan_response(target_id='t',strategy='worked_example')
        plan.blocks[1].required=False
        composer=ResponseComposer(plan)
        text=composer.accept(response(block('b1'),block('b2',ids=['missing'])),SOURCES)
        published=composer.publication(sources=SOURCES,references=[],reply=text,response_id='r')
        self.assertEqual(published['status'],'partial');self.assertEqual(published['omitted'],['b2'])
        example=ResponseComposer(plan_response(target_id='t'))
        self.assertIn('非教材原例',example.accept(response(block('b1',provenance='generated_example')),SOURCES))
        example=ResponseComposer(plan_response(target_id='t'))
        result=example.accept(response(block('b1',text='教学示例（非教材原例）：一项模拟实验。',provenance='generated_example')),SOURCES)
        self.assertEqual(result.count('教学示例（非教材原例）'),1)
        example=ResponseComposer(plan_response(target_id='t'))
        result=example.accept(response(block('b1',text='教学示例（非原书例题）：一项模拟实验。',provenance='generated_example')),SOURCES)
        self.assertEqual(result.count('教学示例'),1)

    def test_changed_source_invalidates_repair_cache(self):
        composer=ResponseComposer(plan_response(target_id='t',strategy='contrast'))
        with self.assertRaises(ValueError):composer.accept(response(block('b1')),SOURCES)
        changed=deepcopy(SOURCES);changed[0]['version']='v2'
        with self.assertRaisesRegex(ValueError,'sources_changed'):composer.accept(response(block('b2')),changed)
        self.assertFalse(composer.accepted)

    def test_publication_remaps_citations_and_refuses_changed_body(self):
        sources=deepcopy(SOURCES)
        for s in sources:s['location']['evidence']={'evidence_id':s['source_id']}
        composer=ResponseComposer(plan_response(target_id='t'))
        composer.accept(response(block('b1',ids=['s2'])),sources)
        references=[{'source_index':0,'evidence':{'evidence_id':'s2'}}]
        pub=composer.publication(sources=sources,references=references,reply='学习位置\n\n研究者主动改变的变量是自变量。[1]',response_id='r')
        self.assertEqual(pub['leading_text'],'学习位置');self.assertTrue(pub['blocks'][0]['rendered_text'].endswith('[1]'))
        with self.assertRaises(ValueError):composer.publication(sources=sources,references=references,reply='被另一个写手改掉',response_id='r')

    def test_one_generation_and_no_json_draft_reaches_student(self):
        text=response(block('b1'))
        class Streaming(ScriptedLLM):
            def chat_with_tools(self,messages,tools,**kwargs):
                if kwargs.get('on_delta'):kwargs['on_delta'](text)
                return super().chat_with_tools(messages,tools,**kwargs)
        llm=Streaming([final_round(text)]);events=[]
        answer=AnswerEvents(lambda e,d:events.append((e,d)));answer.bind(lambda:{'task_id':'t'},lambda:None)
        token=current_answer.set(answer)
        try:
            result=LocalAgentLoop(llm).run(request(llm,ToolRegistry(),initial_sources=deepcopy(SOURCES),
                response_composer=ResponseComposer(plan_response(target_id='t')),publish_gate=lambda *_:(True,'')))
        finally:current_answer.reset(token)
        self.assertTrue(result.completed);self.assertEqual(len(llm.calls),1)
        self.assertFalse(any(e=='answer_delta' for e,_ in events))
        self.assertNotIn('"blocks"',result.final_text)
        self.assertIn('s1',llm.calls[0]['messages'][-1]['content'])

    def test_loop_repairs_only_failed_block_once_and_cancel_does_not_generate(self):
        composer=ResponseComposer(plan_response(target_id='t',strategy='contrast'))
        llm=ScriptedLLM([final_round(response(block('b1'),block('b2',ids=['bad']))),final_round(response(block('b2')))])
        result=LocalAgentLoop(llm).run(request(llm,ToolRegistry(),initial_sources=deepcopy(SOURCES),response_composer=composer))
        self.assertTrue(result.completed);self.assertEqual(len(llm.calls),2)
        self.assertIn('"pending": ["b2"]',llm.calls[1]['messages'][-1]['content'])
        cancellation=Cancellation();cancellation.cancel();never=ScriptedLLM([])
        stopped=LocalAgentLoop(never).run(request(never,ToolRegistry(),cancellation=cancellation,
            response_composer=ResponseComposer(plan_response(target_id='t'))))
        self.assertFalse(stopped.completed);self.assertEqual(never.calls,[])

    def test_invalid_payload_diagnostic_and_forced_finish_do_not_expose_json(self):
        composer=ResponseComposer(plan_response(target_id='t'))
        with self.assertRaises(ValueError) as caught:
            composer.accept(response(dict(block('b1'),expected_answer='PRIVATE_TEST_KEY')),SOURCES)
        self.assertNotIn('PRIVATE_TEST_KEY',str(caught.exception))
        llm=ScriptedLLM([final_round(''),LLMError('受控断线',partial_text='{"private":"DRAFT"}')])
        result=LocalAgentLoop(llm).run(request(llm,ToolRegistry(),initial_sources=deepcopy(SOURCES),
            response_composer=ResponseComposer(plan_response(target_id='t'))))
        self.assertFalse(result.completed);self.assertEqual(result.unpublished_draft,'')
