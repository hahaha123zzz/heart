"""宿主全书候选编排：复用上游引擎、冻结、工作循环和写锁。"""
from pathlib import Path
from dataclasses import asdict,is_dataclass
from types import SimpleNamespace
import asyncio,json,time,os
from . import engine,ingress,storage
from .config import HostEmbedding,HostModel,Metrics,build_llm_model_func,build_embedding_func
from .course_input import freeze,verify,convert,visual_inventory,digest,COURSE
from .roles import resolve_query_roles
from .indexing_policy import _fingerprint,IndexingModelChangedError
from .file_io import atomic_write_json
from .worker import run_in_worker_loop
from .write_lock import write_ownership
from llm.client import LLMClient


def _row(row): return asdict(row) if is_dataclass(row) else dict(row)
def _status(row):
    value=_row(row).get("status", "missing")
    return str(getattr(value,"value",value))

def _resource():
    import psutil
    process=psutil.Process()
    return {"rss_bytes":process.memory_info().rss,"cpu_seconds":sum(process.cpu_times()[:2]),
            "system_available_bytes":psutil.virtual_memory().available,
            "sampled_at":time.time()}

async def embedding_config(metrics=None):
    # 权重哈希随候选固定；使用现有本地 FastEmbed CPU 入口。
    from knowledge.hybrid_retrieval import _embedder_on_device
    model=await asyncio.to_thread(_embedder_on_device,"BAAI/bge-small-zh-v1.5","cpu")
    inner=getattr(model,"model",getattr(model,"_model",None))
    paths=[]
    for obj in (model,inner,getattr(inner,"model",None)):
        for key in ("_model_dir","model_dir","model_path","_model_path"):
            value=getattr(obj,key,None)
            if isinstance(value,(str,Path)) and Path(value).exists(): paths.append(Path(value))
    files={}
    for path in paths:
        for item in (path.rglob("*") if path.is_dir() else [path]):
            if item.is_file() and item.suffix.lower() in (".onnx",".json",".txt"):
                files[item.name]=digest(item)
    if not files: raise RuntimeError("无法固定本地 embedding 权重签名")
    return HostEmbedding(metrics=metrics,weights_sha256=_fingerprint(files))

async def build_book(source, base, *, retries=2, resume_candidate=None):
    if not isinstance(retries,int) or not 0<=retries<=3: raise ValueError("重试次数必须为0到3")
    if resume_candidate is None:
        candidate,manifest=await asyncio.to_thread(freeze,source,base)
    else:
        candidate=Path(resume_candidate).resolve(strict=True)
        manifest=json.loads((candidate/"input_manifest.json").read_text(encoding="utf-8"))
        if Path(manifest["source_root"]).resolve()!=Path(source).resolve():
            raise ValueError("恢复任务的教材根与已接受任务不同")
        verify(candidate/"input",manifest["files"]);verify(Path(source),manifest["files"])
    with write_ownership(candidate):
        metrics=Metrics(candidate/"usage.json")
        if metrics.path.exists():
            previous=json.loads(metrics.path.read_text(encoding="utf-8"))
            metrics.calls=previous["calls"];metrics.embedding_batches=previous["embedding_batches"]
            metrics.embedding_texts=previous["embedding_texts"]
        embedding=await embedding_config(metrics)
        client=LLMClient()
        if client.mock or not client.api_key: raise RuntimeError("缺少真实模型配置")
        models={role:HostModel(client,metrics,role) for role in ("extract","vlm")}
        vision_client=LLMClient(model=client.vision_model)
        models["vlm"]=HostModel(vision_client,metrics,"vlm")
        policy={"extract":models["extract"].identity,"vlm":models["vlm"].identity,
                "embedding_signature":embedding.signature(),"input_signature":manifest["input_signature"],
                "sdk":"1.5.7","chunk_token_size":1200,"llm_concurrency":2,"files_concurrency":1,
                "gleaning":0,"image_analysis":True}
        policy_path=candidate/"policy.json"
        if policy_path.exists() and json.loads(policy_path.read_text(encoding="utf-8"))!=policy:
            raise IndexingModelChangedError("候选模型/参数发生变化，需要新的候选版本")
        atomic_write_json(policy_path,policy)
        working=candidate/"index";working.mkdir(exist_ok=True)
        state_path=candidate/"progress.json"
        state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
            "schema":1,"state":"queued","input_signature":manifest["input_signature"],
            "course_status":manifest["status"],"started_at":time.time(),"runs":[],
            "chapters":{str(c):{"chapter_id":c,"status":"queued","attempts":[]} for c in range(1,12)}}
        run={"started_at":time.time(),"resource_start":_resource(),"resumed":bool(state["runs"])}
        state["runs"].append(run)
        def save():
            state["resource_latest"]=_resource()
            state["peak_sampled_rss_bytes"]=max(state.get("peak_sampled_rss_bytes",0),state["resource_latest"]["rss_bytes"])
            atomic_write_json(state_path,state)
        snapshot=SimpleNamespace(extract=SimpleNamespace(config=models["extract"],owner=None),
            vlm=SimpleNamespace(config=models["vlm"],owner=None),embedding_config=embedding,
            limits={"extract":{"max_async":2,"timeout":180},"vlm":{"max_async":1,"timeout":180}})
        visuals,_,_=visual_inventory(candidate/"input")
        staged=[];source_maps={}
        for chapter in range(1,12):
            source_file,parsed,mapping=convert(candidate/"input",chapter,visual_map=visuals)
            source_maps[source_file.name]=mapping
            if (ingress.bundles_root(working)/f"{source_file.name}.bundle").exists():
                frozen,bundle=ingress.load_verified_bundle(working,source_file.name)
                item=ingress.StagedDocument(canonical_name=source_file.name,
                    source_path=ingress.pending_root(working)/source_file.name,bundle_dir=bundle,
                    manifest_path=bundle/ingress.MANIFEST_FILENAME,process_options=frozen["process_options"],
                    chunk_options=frozen["chunk_options"],audit_ledger=frozen.get("block_policy"))
            else: item=ingress.freeze_document(working,source_file,parsed)
            staged.append(item)
            state["chapters"][str(chapter)]["canonical_name"]=source_file.name
        atomic_write_json(candidate/"source_map.json",source_maps)
        verify(candidate/"input",manifest["files"]);verify(Path(manifest["source_root"]),manifest["files"])
        # 所有11章已排队；预检只验证服务，不设置单章验收门槛。
        if not (candidate/"preflight.json").exists():
            started=time.monotonic()
            result=await build_llm_model_func(llm_config=models["extract"])("Reply READY only.")
            await build_embedding_func(embedding_config=embedding)(["实验心理学"])
            atomic_write_json(candidate/"preflight.json",{"model_response":result,"seconds":time.monotonic()-started,
                "embedding_signature":embedding.signature(),"resource":_resource()})
        async def job(bridge):
            rag=engine.build_rag(working,io_bridge=bridge,enable_vlm=True,indexing_snapshot=snapshot)
            failed=True
            ids=[engine._document_id(item.canonical_name) for item in staged]
            try:
                await engine.initialize(rag)
                # 只修复本适配器产生且已核验冻结输入对应的 Windows URI；不重解析教材。
                from .paths import sidecar_uri_for
                from lightrag.utils_pipeline import sidecar_blocks_path
                for item,doc_id in zip(staged,ids):
                    full=await rag.full_docs.get_by_id(doc_id)
                    if full and full.get("parse_engine")==engine.PARSER_ENGINE:
                        directory=ingress.pending_root(working)/"__parsed__"/(item.canonical_name+".parsed")
                        expected_uri=sidecar_uri_for(directory)
                        if not sidecar_blocks_path(expected_uri): raise ingress.IngressError("恢复所需 sidecar 结构块缺失")
                        if full.get("sidecar_location")!=expected_uri:
                            await rag.full_docs.upsert({doc_id:{**full,"sidecar_location":expected_uri}})
                existing=await rag.doc_status.get_docs_by_ids(ids,strict=True)
                missing=[item for item,doc_id in zip(staged,ids) if doc_id not in existing]
                if missing:
                    track=await engine.enqueue(rag,missing)
                    if not isinstance(track,str) or not track: raise engine.LightRagContractError("缺少 track_id")
                    state["track_ids"]=state.get("track_ids",[])+[track]
                async def refresh():
                    rows=await engine.document_records(rag,ids)
                    for chapter,doc_id in enumerate(ids,1):
                        entry=state["chapters"][str(chapter)];row=rows.get(doc_id)
                        entry.update(status=_status(row) if row is not None else "missing",doc_id=doc_id)
                        if row is not None:
                            record=_row(row);entry.update(chunks=len(record.get("chunks_list") or []),
                                chunk_ids=record.get("chunks_list") or [],error=record.get("error_msg") or "")
                            if entry["status"]=="failed":
                                failures=entry.setdefault("failures",[])
                                if not failures or failures[-1]["error"]!=entry["error"] or failures[-1]["run"]!=len(state["runs"]):
                                    failures.append({"observed_at":time.time(),"run":len(state["runs"]),"error":entry["error"]})
                    save();return rows
                for attempt in range(retries+1):
                    bridge.raise_if_cancelled()
                    if (candidate/"cancel.request").exists(): raise asyncio.CancelledError()
                    verify(candidate/"input",manifest["files"]);verify(Path(manifest["source_root"]),manifest["files"])
                    await refresh()
                    pending=[e for e in state["chapters"].values() if e["status"]!="processed"]
                    if not pending: break
                    for entry in pending: entry["attempts"].append({"run":len(state["runs"]),"attempt":attempt+1,"time":time.time()})
                    state["state"]="processing";save()
                    if any(entry["status"]=="failed" for entry in pending):
                        await engine.request_retry_failed(rag)
                    processor=asyncio.create_task(rag.apipeline_process_enqueue_documents())
                    try:
                        while not processor.done():
                            await refresh();bridge.raise_if_cancelled()
                            if (candidate/"cancel.request").exists(): raise asyncio.CancelledError()
                            await asyncio.wait({processor},timeout=5)
                        await processor
                    finally:
                        if not processor.done():
                            processor.cancel();await asyncio.gather(processor,return_exceptions=True)
                    await refresh()
                rows=await refresh()
                nodes=await rag.chunk_entity_relation_graph.get_all_nodes()
                edges=await rag.chunk_entity_relation_graph.get_all_edges()
                for chapter,doc_id in enumerate(ids,1):
                    entry=state["chapters"][str(chapter)];chunks=set(entry.get("chunk_ids",[]))
                    entry["entities"]=sum(bool(chunks & set(str(n.get("source_id","")).split("<SEP>"))) for n in nodes)
                    entry["relationships"]=sum(bool(chunks & set(str(e.get("source_id","")).split("<SEP>"))) for e in edges)
                    entry["complete"]=entry["status"]=="processed" and bool(chunks) and entry["entities"]>0 and entry["relationships"]>0
                state["graph"]={"entities":len(nodes),"relationships":len(edges),
                                "chunks":sum(e.get("chunks",0) for e in state["chapters"].values())}
                complete=all(e.get("complete") for e in state["chapters"].values())
                state["state"]="candidate_complete" if complete else "partial_failed"
                verify(candidate/"input",manifest["files"]);verify(Path(manifest["source_root"]),manifest["files"])
                if complete:
                    storage.write_meta(working,indexing_policy=policy,embedding_config=embedding,state="candidate_complete")
                failed=not complete
                return complete
            finally: await engine.finalize(rag,cancel_pending=failed)
        try:
            await run_in_worker_loop(job)
            if state["state"]=="candidate_complete":
                files={}
                for path in storage._store_root(working).iterdir():
                    if path.is_file() and (path.name.startswith("vdb_") or path.name in (
                        "graph_chunk_entity_relation.graphml","kv_store_text_chunks.json","kv_store_doc_status.json","kv_store_full_docs.json")):
                        files[path.relative_to(working).as_posix()]=digest(path)
                atomic_write_json(candidate/"index_files.json",files)
        except asyncio.CancelledError:
            state["state"]="cancelled";raise
        except BaseException as exc:
            state["state"]="failed";state["error_type"]=type(exc).__name__;raise
        finally:
            run["ended_at"]=time.time();run["elapsed_seconds"]=run["ended_at"]-run["started_at"]
            run["resource_end"]=_resource();state["usage"]=metrics.public();save()
        return candidate,state
