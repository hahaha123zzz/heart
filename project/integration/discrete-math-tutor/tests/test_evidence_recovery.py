import unittest
from types import SimpleNamespace
from knowledge.textbook import TextbookChunk
from knowledge.evidence_recovery import recover_evidence

class RecoveryTests(unittest.TestCase):
    def chunk(self,text,id):
        return TextbookChunk('教材','欧拉图',text,frozenset(),chunk_id=id)
    def test_append_deduplicated_sources_and_preserve_original_order(self):
        old=self.chunk('握手定理',1);new=self.chunk('欧拉回路定义',2);calls=[]
        def retrieve(query, fallback, **kwargs):
            calls.append(query);return [old,new,new]
        result=recover_evidence('所有图有欧拉回路是否成立？',[old],[],SimpleNamespace(status='insufficient',missing=['欧拉回路定义']),retrieve)
        self.assertEqual(result,[old,new]);self.assertEqual(calls,['欧拉回路定义'])
    def test_no_recovery_for_unavailable_conflicting_or_nonjudgement(self):
        old=self.chunk('正文',1)
        def retrieve(*args,**kwargs):
            self.fail('不应进行补检索')
        for status in ['unavailable','conflicting','sufficient']:
            self.assertEqual(recover_evidence('结论是否成立',[old],[],SimpleNamespace(status=status,missing=['定义']),retrieve),[old])
        self.assertEqual(recover_evidence('解释数据库实现',[old],[],SimpleNamespace(status='partial',missing=['数据库定义']),retrieve),[old])
    def test_bounded_append_even_if_retriever_returns_excess(self):
        old=self.chunk('原文',1)
        result=recover_evidence('是否正确？',[old],[],SimpleNamespace(status='partial',missing=['定义'*500]),lambda *a,**k:[self.chunk(str(i),i) for i in range(2,20)])
        self.assertEqual(len(result),4)
    def test_missing_items_are_not_joined_with_numbered_anchor(self):
        old=self.chunk('原文',1);calls=[]
        def retrieve(query,fallback,**kwargs):
            calls.append(query);return [old]
        recover_evidence('是否成立',[old],[],SimpleNamespace(status='partial',missing=['欧拉回路定义','定理7.1的关联']),retrieve)
        self.assertEqual(calls,['欧拉回路定义','定理7.1的关联'])
    def test_explicit_cross_chapter_request_recovers_missing_evidence(self):
        old=self.chunk('函数核是等价关系',1);new=self.chunk('等价类构成划分',2)
        result=recover_evidence('定理10.6为什么能得到划分？指出第9章依据。',[old],[],SimpleNamespace(status='partial',missing=['第9章等价类与划分的定理']),lambda *a,**k:[new])
        self.assertEqual(result,[old,new])
