"""固定 SDK、结构转换、来源与失败边界。"""
import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from knowledge.lightrag import engine,ingress
from knowledge.lightrag.config import _run_adapter_with_retry,HostEmbedding
from knowledge.lightrag.course_input import inventory,verify,convert,visual_inventory
from knowledge.lightrag.retrieval import map_chunks,LightRagBackend,as_textbook_chunk
from knowledge.lightrag.file_io import atomic_write_json
from knowledge.lightrag.write_lock import write_ownership
from knowledge.lightrag.indexing_policy import IndexingPolicyError

class ContractTests(unittest.TestCase):
    def test_windows_sidecar_uri_roundtrip(self):
        from knowledge.lightrag.paths import sidecar_uri_for
        from lightrag.utils_pipeline import sidecar_blocks_path
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"中文 sidecar";directory.mkdir()
            blocks=directory/"document.blocks.jsonl";blocks.write_text("{}")
            self.assertEqual(Path(sidecar_blocks_path(sidecar_uri_for(directory))),blocks)

    def test_exact_version(self):
        self.assertEqual(engine.installed_version(),"1.5.7")
        with patch.object(engine,"installed_version",return_value="1.5.8"):
            with self.assertRaises(engine.LightRagContractError): engine._require_exact_version()

    def test_structured_query_never_generates_answer(self):
        class R:
            async def aquery_data(self,query,param):
                self.param=param
                return {"status":"success","data":{key:[] for key in ("chunks","entities","relationships","references")},"metadata":{"query_mode":param.mode}}
            async def aquery_llm(self,*args,**kwargs): raise AssertionError("不得生成答案")
        rag=R();answer,records=asyncio.run(engine.query_with_sources(rag,"教材概念"))
        self.assertEqual(answer,"");self.assertEqual(rag.param.mode,"hybrid")
        self.assertEqual([r["kind"] for r in records],["query_metadata"])

    def test_failure_is_explicit(self):
        class R:
            async def aquery_data(self,*args,**kwargs): return {"status":"failure","message":"SDK backend unavailable"}
        with self.assertRaisesRegex(engine.LightRagContractError,"unavailable"):
            asyncio.run(engine.query_with_sources(R(),"教材概念"))

    def test_no_results_is_empty_not_failure_disguised(self):
        class R:
            async def aquery_data(self,*args,**kwargs):
                return {"status":"failure","message":"Query returned no results","metadata":{"failure_reason":"no_results"}}
        self.assertEqual(asyncio.run(engine.query_with_sources(R(),"教材外问题")),("",[]))

    def test_shape_validation(self):
        class R:
            async def aquery_data(self,*args,**kwargs): return {"status":"success","data":{"chunks":"bad"},"metadata":{}}
        with self.assertRaises(engine.LightRagContractError): asyncio.run(engine.query_with_sources(R(),"教材概念"))

    def test_unsupported_mode_rejected(self):
        with self.assertRaises(ValueError): asyncio.run(engine.query_with_sources(None,"教材概念","invalid"))

    def test_q2_declared_snapshot_identity(self):
        from knowledge.lightrag.course_input import declared_snapshot
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp);root=parent/"course";root.mkdir()
            (root/"manifest.json").write_text("fixed")
            files=[{"path":"manifest.json","size":5,"sha256":hashlib.sha256(b"fixed").hexdigest()}]
            identity=hashlib.sha256(json.dumps(files,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            report={"schema":"full-course-inputs-v1","files":files,"snapshot_id":identity,
                    "chapters":[{"chapter_id":n} for n in range(1,12)],"ready":False,"course_status":"staging"}
            atomic_write_json(parent/"input_manifest.json",report)
            self.assertEqual(declared_snapshot(root)["snapshot_id"],identity)
            (root/"manifest.json").write_text("drift")
            with self.assertRaises(ingress.IngressError):declared_snapshot(root)

    def test_rendered_crops_are_not_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"manifest.json").write_text("original")
            expected=inventory(root);(root/"crops").mkdir();(root/"crops/new.png").write_bytes(b"derived")
            verify(root,expected)

    def test_snapshot_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"manifest.json").write_text("original")
            expected=inventory(root);verify(root,expected)
            (root/"manifest.json").write_text("changed")
            with self.assertRaises(ingress.IngressError): verify(root,expected)

    def test_snapshot_new_file_and_wal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"manifest.json").write_text("original");expected=inventory(root)
            (root/"pdf_manifest.json").write_text("new")
            with self.assertRaises(ingress.IngressError):verify(root,expected)
            (root/"rag_index.sqlite3-wal").write_text("pending")
            with self.assertRaises(ingress.IngressError):inventory(root)

    def test_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ingress.IngressError):ingress.load_verified_bundle(Path(temp),"../outside.pdf")

    def test_cross_process_lock_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"candidate"
            with write_ownership(root):
                with self.assertRaises(IndexingPolicyError):
                    with write_ownership(root): pass

    def test_mapping_ignores_summary_and_metadata(self):
        text="自变量是研究者主动操纵的实验条件，需要保持教材原始文字范围。"
        doc={"chapter_id":2,"source":"chapter2.txt","document_id":"course:chapter-02","version":"abc", "blocks":[
            {"block_index":34,"kind":"paragraph","section_id":2,"section":"自变量","text":text}]}
        records=[{"kind":"entity","content":text,"source":"chapter.pdf"},
                 {"kind":"query_metadata","content":text},
                 {"kind":"chunk","content":text,"source":"chapter.pdf","chunk_id":"native"}]
        rows=map_chunks(records,{"chapter.pdf":doc});self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["text"],text);self.assertEqual(rows[0]["version"],"abc")
        self.assertIsNone(rows[0]["page"])
        self.assertEqual(as_textbook_chunk(rows[0]).source_spans[0]["block_id"],34)
        self.assertEqual(map_chunks(records[:2],{"chapter.pdf":doc}),[])

    def test_unregistered_source_rejected(self):
        with self.assertRaises(engine.LightRagContractError):
            map_chunks([{"kind":"chunk","source":"unknown","content":"text"}],{})

    def test_not_ready_and_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            backend=LightRagBackend(temp,authorized_course_ids=[])
            with self.assertRaises(PermissionError):backend.validate("experimental-psychology-3")
            backend=LightRagBackend(temp,authorized_course_ids=["experimental-psychology-3"])
            atomic_write_json(Path(temp)/"input_manifest.json",{"course_id":"experimental-psychology-3"})
            atomic_write_json(Path(temp)/"progress.json",{"state":"partial_failed","chapters":{}})
            with self.assertRaisesRegex(RuntimeError,"激活"):backend.validate("experimental-psychology-3")
            backend.allow_candidate=True
            with self.assertRaisesRegex(RuntimeError,"完整"):backend.validate("experimental-psychology-3")

    def test_table_summary_uses_original_pointer(self):
        text="原始表格单元格中的实验变量和控制方式必须保持不变。"
        doc={"chapter_id":2,"source":"ch2.txt","document_id":"doc2","version":"v", "blocks":[
            {"block_index":7,"kind":"table","section_id":1,"section":"表格","text":text,"rows":[[text]]}]}
        record={"kind":"chunk","source":"ch2.pdf","chunk_id":"sdk","content":"这是模型生成的摘要，不能作为原文。"}
        self.assertEqual(map_chunks([record],{"ch2.pdf":doc}),[])
        record["original_blocks"]=[{"kind":"table","block_index":7}]
        rows=map_chunks([record],{"ch2.pdf":doc})
        self.assertEqual(rows[0]["text"],text)
        self.assertNotIn("模型生成",rows[0]["quote"])

    def test_cancelled_query_checks_before_any_io(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            backend=LightRagBackend(temp,authorized_course_ids=[])
            cancel=SimpleNamespace(is_cancelled=lambda:True)
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(backend.search("教材概念",course_id="experimental-psychology-3",cancellation=cancel))

    def test_embedding_signature_includes_weights(self):
        self.assertNotEqual(HostEmbedding(weights_sha256="a").signature(),HostEmbedding(weights_sha256="b").signature())

    def test_cancel_does_not_retry(self):
        calls=[]
        async def run():
            async def request(): calls.append(1);raise asyncio.CancelledError()
            await _run_adapter_with_retry(request,io_bridge=None)
        with self.assertRaises(asyncio.CancelledError):asyncio.run(run())
        self.assertEqual(len(calls),1)

    def test_finalize_preserves_embedding_until_flush(self):
        from types import SimpleNamespace
        for cancelled in (False,True):
            events=[]
            def queue(name):
                async def func():pass
                async def shutdown(**kwargs):events.append((name,kwargs["graceful"]))
                func.shutdown=shutdown
                return func
            model=queue("model");embed=queue("embedding")
            async def flush():
                self.assertFalse(any(name=="embedding" for name,_ in events))
                if cancelled:self.assertIn(("model",False),events)
                events.append(("flush",True))
            rag=SimpleNamespace(role_llm_funcs={"extract":model},embedding_func=SimpleNamespace(func=embed),
                                finalize_storages=flush)
            asyncio.run(engine.finalize(rag,cancel_pending=cancelled))
            self.assertEqual(events[-1],("embedding",not cancelled))
            self.assertEqual(sum(name=="model" for name,_ in events),1)

    def test_proxy_thinking_and_truncation_usage(self):
        from types import SimpleNamespace
        from knowledge.lightrag.config import HostModel,Metrics,build_llm_model_func
        metrics=Metrics();sent=[]
        response=SimpleNamespace(model="deepseek-flash",choices=[SimpleNamespace(finish_reason="length",message=SimpleNamespace(content="incomplete"))],
                                 usage=SimpleNamespace(model_dump=lambda:{"total_tokens":8192}))
        class Client:
            def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self)
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def create(self,**kwargs):sent.append(kwargs);return response
        host=HostModel(SimpleNamespace(model="deepseek-flash",base_url="https://proxy.example/v1",api_key="fixture",mock=False),metrics)
        self.assertEqual(host.identity["thinking"],"disabled")
        with patch("openai.AsyncOpenAI",Client):
            with self.assertRaisesRegex(RuntimeError,"截断"):
                asyncio.run(build_llm_model_func(llm_config=host)("extract"))
        self.assertEqual(sent[0]["extra_body"],{"thinking":{"type":"disabled"}})
        self.assertEqual(metrics.public()["usage"]["total_tokens"],8192)
        self.assertEqual(metrics.calls[0]["status"],"failed")

    def test_nonretryable_does_not_retry(self):
        calls=[]
        async def run():
            async def request():calls.append(1);raise ValueError("invalid")
            await _run_adapter_with_retry(request,io_bridge=None)
        with self.assertRaises(ValueError):asyncio.run(run())
        self.assertEqual(len(calls),1)

    def test_transient_retry_is_bounded(self):
        calls=[]
        async def run():
            async def request():calls.append(1);raise ConnectionError("temporary")
            with patch("knowledge.lightrag.config.asyncio.sleep",new=__import__("unittest.mock",fromlist=["AsyncMock"]).AsyncMock()):
                await _run_adapter_with_retry(request,io_bridge=None)
        with self.assertRaises(ConnectionError):asyncio.run(run())
        self.assertEqual(len(calls),3)

if __name__=="__main__":unittest.main()
