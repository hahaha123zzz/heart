"""不加载模型/启动器或联网，证明验收包装一次调用及异常/取消语义。"""
import asyncio
from types import SimpleNamespace
import unittest
from scripts.lightrag_acceptance_instrumentation import wrap_native_query


class NativeAcceptanceWrapperTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = {'mode':'normal','events':[]}
        self.rag = SimpleNamespace(llm_response_cache=SimpleNamespace(global_config={}))
        self.calls = []

    def event(self, kind, **fields):
        self.state['events'].append({'event':kind, **fields})

    async def test_original_called_once_despite_launcher_global_rebinding(self):
        async def original(rag, text, **kwargs):
            self.calls.append((rag,text,kwargs));return 'original result'
        wrapped=wrap_native_query(original,state=self.state,event=self.event)
        namespace={'query':original};namespace['query']=wrapped
        self.assertEqual(await namespace['query'](self.rag,'query',mode='hybrid'),'original result')
        self.assertEqual(self.calls,[(self.rag,'query',{'mode':'hybrid'})])
        self.assertFalse(self.rag.llm_response_cache.global_config['enable_llm_cache'])
        self.assertEqual(self.state['events'][-1],{'event':'query_end','status':'success'})

    async def test_exception_is_not_retried_or_replaced(self):
        failure=ValueError('fixture original failure')
        async def original(*args):self.calls.append(1);raise failure
        with self.assertRaises(ValueError) as caught:
            await wrap_native_query(original,state=self.state,event=self.event)(self.rag)
        self.assertIs(caught.exception,failure);self.assertEqual(self.calls,[1])
        self.assertEqual(self.state['events'][-1]['status'],'ValueError')

    async def test_original_cancelled_error_propagates_once(self):
        async def original(*args):self.calls.append(1);raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await wrap_native_query(original,state=self.state,event=self.event)(self.rag)
        self.assertEqual(self.calls,[1]);self.assertEqual(self.state['events'][-1]['status'],'CancelledError')

    async def test_timeout_waits_for_this_call_sdk_start_and_original_cleanup(self):
        self.state['mode']='timeout';self.event('sdk_start')
        cleanup=[]
        async def original(*args):
            self.calls.append(1);await asyncio.sleep(.03);self.event('sdk_start')
            try:await asyncio.sleep(10)
            finally:cleanup.append(True)
        with self.assertRaises(TimeoutError):
            await wrap_native_query(original,state=self.state,event=self.event)(self.rag)
        self.assertEqual(self.calls,[1]);self.assertEqual(cleanup,[True])
        self.assertEqual(self.state['events'][-1]['status'],'TimeoutError')

    async def test_external_cancel_propagates_and_joins_original(self):
        started=asyncio.Event();cleanup=[];self.state['mode']='timeout'
        async def original(*args):
            self.calls.append(1);started.set()
            try:await asyncio.sleep(10)
            finally:cleanup.append(True)
        task=asyncio.create_task(wrap_native_query(original,state=self.state,event=self.event)(self.rag))
        await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.calls,[1]);self.assertEqual(cleanup,[True])
        self.assertEqual(self.state['events'][-1]['status'],'CancelledError')


if __name__=='__main__':unittest.main()
