"""真实固定SDK + 替身LLM/向量：失败、原生重试、非空图和重启恢复。"""
import asyncio,json,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from knowledge.lightrag import engine,ingress,storage
from knowledge.lightrag.parse_types import ParsedDocument
from knowledge.lightrag.file_io import atomic_write_json

async def check(root):
    import numpy as np
    from lightrag.utils import EmbeddingFunc
    from lightrag.llm_roles import RoleLLMConfig
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    source=root/"source";source.mkdir(exist_ok=True);working=root/"index";working.mkdir(exist_ok=True)
    failures={"enabled":True};calls=[]
    async def llm(prompt="",**kwargs):
        calls.append(1)
        if failures["enabled"] and "MUST_FAIL" in prompt: raise ValueError("injected deterministic failure")
        return "entity<|#|>Alpha<|#|>Concept<|#|>Alpha links Beta.\nentity<|#|>Beta<|#|>Concept<|#|>Beta is linked by Alpha.\nrelation<|#|>Alpha<|#|>Beta<|#|>links<|#|>Alpha links Beta.\n<|COMPLETE|>"
    async def embed(texts,**kwargs):return np.asarray([[1.,2.,3.] for _ in texts],dtype=np.float32)
    def make():
        engine._require_exact_version();engine._register_parser()
        return engine._controlled_class()(working_dir=str(working),workspace=engine.workspace_for(working),
            llm_model_func=llm,llm_model_name="deterministic-test",embedding_func=EmbeddingFunc(embedding_dim=3,func=embed),
            role_llm_configs={"extract":RoleLLMConfig(func=llm,max_async=1)},
            entity_extract_max_gleaning=0,max_parallel_insert=1,auto_manage_storages_states=False)
    staged=[]
    for name,content in (("good.txt","Alpha links Beta in this test."),("bad.txt","MUST_FAIL: Alpha links Beta in this test.")):
        path=source/name;path.write_text(content,encoding="utf-8")
        staged.append(ingress.freeze_document(working,path,ParsedDocument(markdown=content,engine="test")))
    ids=[engine._document_id(item.canonical_name) for item in staged]
    rag=make();await engine.initialize(rag)
    try:
        await engine.enqueue(rag,staged);await rag.apipeline_process_enqueue_documents()
        rows=await engine.document_records(rag,ids)
        states={key:str(getattr(row["status"],"value",row["status"])) for key,row in rows.items()}
        assert sorted(states.values())==["failed","processed"],states
        assert storage.has_output(working)
        partial=dict(states)
        await engine.finalize(rag,cancel_pending=True)
        rag=make();await engine.initialize(rag)
        failures["enabled"]=False
        await engine.request_retry_failed(rag);await rag.apipeline_process_enqueue_documents()
        rows=await engine.document_records(rag,ids)
        assert all(str(getattr(row["status"],"value",row["status"]))=="processed" for row in rows.values())
        assert all(row["chunks_list"] for row in rows.values())
        nodes=await rag.chunk_entity_relation_graph.get_all_nodes();edges=await rag.chunk_entity_relation_graph.get_all_edges()
        assert len(nodes)==2 and len(edges)==1,(len(nodes),len(edges))
    finally:await engine.finalize(rag,cancel_pending=False)
    previous_calls=len(calls)
    rag=make();await engine.initialize(rag)
    try:
        rows=await engine.document_records(rag,ids)
        await rag.apipeline_process_enqueue_documents()
        assert len(calls)==previous_calls,"重启不得重新生成已处理文档"
        assert len(rows)==2
        class KnownKeywords:
            async def aquery_data(self,question,param):
                param.hl_keywords=["Alpha"];param.ll_keywords=["Beta"]
                return await rag.aquery_data(question,param=param)
        answer,records=await engine.query_with_sources(KnownKeywords(),"Alpha Beta")
        assert answer=="" and all(any(row["kind"]==kind for row in records) for kind in
                                  ("chunk","entity","relationship","reference","query_metadata"))
    finally:await engine.finalize(rag,cancel_pending=False)
    return {"sdk":"1.5.7","model":"deterministic substitute; no remote model", "partial_failure":partial,
            "structured_sdk_context_passed":True,"query_generation":"none; deterministic supplied keywords","partial_finalize_restart_passed":True,"native_retry_passed":True,"restart_passed":True,"entities":len(nodes),"relationships":len(edges),
            "llm_calls":len(calls),"source_scope":"isolated temporary fixtures"}
if __name__=="__main__":
    target=ROOT/".runtime/lightrag-sdk-check";target.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with tempfile.TemporaryDirectory(dir=target) as temp:report=asyncio.run(check(Path(temp)))
    report["elapsed_seconds"]=time.monotonic()-started
    atomic_write_json(target/"report.json",report);print(json.dumps(report,ensure_ascii=False))
