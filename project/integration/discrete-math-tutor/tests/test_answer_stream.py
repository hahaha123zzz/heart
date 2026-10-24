"""真实迭代器契约：输出发生在 SDK 流关闭前，失败不能透明重播。"""
import unittest
from types import SimpleNamespace as N
from unittest.mock import Mock
from llm.client import LLMClient, LLMError


def chunk(text='', reason=None, calls=None, usage=None):
    return N(choices=[N(index=0, delta=N(content=text, tool_calls=calls), finish_reason=reason)], usage=usage)


class Stream:
    def __init__(self, items): self.items, self.closed = items, False
    def __iter__(self):
        for item in self.items:
            if isinstance(item, Exception): raise item
            yield item
    def close(self): self.closed = True


class AnswerStreamTests(unittest.TestCase):
    def test_full_source_validation_is_not_repeated_for_every_token(self):
        from llm.answer_events import AnswerEvents
        full, live = Mock(), Mock()
        publisher = AnswerEvents(lambda *_: None)
        publisher.bind(lambda: {'task_id': 't', 'task_revision': 1}, full, live)
        publisher.begin()
        for _ in range(30):
            publisher.guard()
            publisher.delta('字')
        full.assert_called_once()
        self.assertEqual(live.call_count, 60)
        full.side_effect = ValueError('教材版本已改变')
        with self.assertRaisesRegex(ValueError, '教材版本'):
            publisher.checking()

    def test_full_source_validation_is_not_repeated_for_every_token(self):
        from llm.answer_events import AnswerEvents
        full, live = Mock(), Mock()
        publisher = AnswerEvents(lambda *_: None)
        publisher.bind(lambda: {'task_id': 't', 'task_revision': 1}, full, live)
        publisher.begin()
        for _ in range(30):
            publisher.guard()
            publisher.delta('字')
        full.assert_called_once()
        self.assertEqual(live.call_count, 60)
        full.side_effect = ValueError('教材版本已改变')
        with self.assertRaisesRegex(ValueError, '教材版本'):
            publisher.checking()

    def test_q3_sdk_tool_round_retracted_then_checked_final(self):
        from agents.agent_loop import LocalAgentLoop, LoopRequest
        from agents.tool_protocol import ToolRegistry
        from tests.test_q3_agent_loop import EchoTool
        from llm.answer_events import AnswerEvents, current_answer
        call=N(index=0,id='tool-1',function=N(name='echo',arguments='{"text":"证据"}'))
        client,sdk,_=self.client([])
        first=Stream([chunk('查询中',calls=[call],reason='tool_calls')]);second=Stream([chunk('最终'),chunk('说明[1]','stop')])
        sdk.chat.completions.create.side_effect=[first,second]
        registry=ToolRegistry();registry.register(EchoTool());events=[]
        publisher=AnswerEvents(lambda e,d:events.append((e,d)));publisher.bind(lambda:{'task_id':'t','task_revision':1},lambda:None)
        token=current_answer.set(publisher)
        try:result=LocalAgentLoop(client).run(LoopRequest(student_id='s',session_id='tab',task_id='t',request_id='r',
            message='解释',system_prompt='教材助教',tools=registry,publish_gate=lambda text,result:(True,'')))
        finally:current_answer.reset(token)
        self.assertTrue(result.completed,result.error);self.assertEqual(result.final_text,'最终说明[1]')
        self.assertTrue(first.closed and second.closed)
        self.assertFalse(any(e=='answer_replace' and d['text']=='' for e,d in events))
        self.assertFalse(any(e=='answer_delta' and '查询中' in d['text'] for e,d in events))
        self.assertEqual(events[-1][1]['state'],'checking')
        states=[d['state'] for e,d in events if e=='answer_state']
        self.assertIn('retrieving',states)
        self.assertNotIn('rejected',states)
        publisher.finish({'answer_status':'quality_rejected'})
        self.assertEqual(events[-1][1]['state'],'rejected')
        tool_messages=[m for m in result.messages if m['role']=='tool'];self.assertEqual(tool_messages[0]['tool_call_id'],'tool-1')
        self.assertFalse(any(e['type']=='answer_delta' for e in result.events))

    def test_request_events_retract_repair_then_authoritative_snapshot(self):
        from llm.answer_events import AnswerEvents, current_answer, answer_kwargs, checking
        events=[];guard=Mock();publisher=AnswerEvents(lambda event,data:events.append((event,data)))
        publisher.bind(lambda:{'task_id':'task','task_revision':2},guard)
        token=current_answer.set(publisher)
        try:
            answer_kwargs()['on_delta']('草稿');checking()
            answer_kwargs()['on_delta']('修订');checking()
            publisher.finish({'answer_status':'answered','reply':'最终编号[2]'})
        finally:current_answer.reset(token)
        self.assertEqual([d['seq'] for _,d in events],list(range(1,len(events)+1)))
        self.assertEqual(len({d['answer_id'] for _,d in events}),1)
        self.assertNotIn(('answer_replace',''),[(e,d.get('text')) for e,d in events])
        self.assertEqual(events[-2][1]['text'],'最终编号[2]')
        self.assertEqual(events[-1][1]['state'],'saved')
        self.assertEqual(answer_kwargs(),{})

    def client(self, items):
        client=LLMClient(api_key='test',base_url='https://example.invalid',mock=False)
        sdk=Mock();sdk.with_options.return_value=sdk;client._client=sdk
        stream=Stream(items);sdk.chat.completions.create.return_value=stream
        return client,sdk,stream

    def test_actual_delta_before_close_and_usage(self):
        client,sdk,stream=self.client([chunk('中'),chunk('文', 'stop',usage=N(prompt_tokens=2,completion_tokens=2,total_tokens=4))])
        seen=[]
        def delta(text):
            self.assertFalse(stream.closed);seen.append(text)
        result=client.chat_with_tools([{'role':'user','content':'问题'}],[],on_delta=delta)
        self.assertEqual(seen,['中','文']);self.assertEqual(result.text,'中文')
        self.assertEqual(result.usage['total_tokens'],4);self.assertTrue(stream.closed)
        self.assertTrue(sdk.chat.completions.create.call_args.kwargs['stream'])
        sdk.with_options.assert_called_once_with(max_retries=0)

    def test_fragmented_tools_and_thinking_do_not_leak(self):
        call=lambda i,id,name,args,extra=None:N(index=i,id=id,function=N(name=name,arguments=args),extra_content=extra)
        client,_,stream=self.client([
            chunk('<thi'),chunk('nk>秘密'),chunk('</think>说明'),
            chunk(calls=[call(1,'b','other','{}'),call(0,'a','retrieve','{"query":')]),
            chunk(calls=[call(0,'a','retrieve','"条件"}',{'google':{'thought_signature':'opaque'}})],reason='tool_calls')])
        seen=[];result=client.chat_with_tools([],[],on_delta=seen.append)
        self.assertEqual(''.join(seen),'说明');self.assertEqual(result.text,'说明')
        self.assertEqual([c.id for c in result.tool_calls],['a','b'])
        self.assertEqual(result.tool_calls[0].name,'retrieve')
        self.assertEqual(result.tool_calls[0].arguments,{'query':'条件'})
        self.assertIn('google',result.tool_calls[0].extra_content);self.assertTrue(stream.closed)

    def test_length_and_incomplete_stream_fail_without_retry(self):
        for items in ([chunk('半份计划','length')],[chunk('半份计划')],[chunk('半份计划'),OSError('断线')]):
            client,sdk,stream=self.client(items)
            with self.assertRaises(LLMError):client.chat([],on_delta=lambda _:None)
            self.assertTrue(stream.closed);sdk.chat.completions.create.assert_called_once()

    def test_guard_cancels_and_closes_without_more_output(self):
        client,sdk,stream=self.client([chunk('第一段'),chunk('不能显示','stop')]);seen=[]
        def guard():
            if seen:raise ValueError('revision changed')
        with self.assertRaises(LLMError):client.chat([],on_delta=seen.append,stream_guard=guard)
        self.assertEqual(seen,['第一段']);self.assertTrue(stream.closed)
        sdk.chat.completions.create.assert_called_once()

    def test_stream_options_rejected_only_before_stream_can_fallback(self):
        client,sdk,stream=self.client([chunk('答案','stop')])
        error=ValueError('unsupported stream_options');error.status_code=400
        sdk.chat.completions.create.side_effect=[error,stream]
        self.assertEqual(client.chat([],on_delta=lambda _:None),'答案')
        self.assertEqual(sdk.chat.completions.create.call_count,2)
        self.assertNotIn('stream_options',sdk.chat.completions.create.call_args.kwargs)

    def test_other_provider_errors_do_not_retry(self):
        client,sdk,_=self.client([]);error=ValueError('invalid key');error.status_code=401
        sdk.chat.completions.create.side_effect=error
        with self.assertRaises(LLMError):client.chat([],on_delta=lambda _:None)
        sdk.chat.completions.create.assert_called_once()


if __name__=='__main__':unittest.main()
