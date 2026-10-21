"""LightRAG 结构化检索及原文映射；不生成正式回答或引用卡。"""
from pathlib import Path
import asyncio,json,math
from . import engine,storage
from .course_input import verify,digest,COURSE
from .pipeline import embedding_config
from .config import Metrics
from .roles import resolve_query_roles
from .worker import run_in_worker_loop
from .write_lock import write_ownership
from .indexing_policy import _fingerprint
from knowledge.source_mapping import source_spans,block_text
from knowledge.grounding_text import normalized
from knowledge.textbook import TextbookChunk,terms_for


async def attach_provenance(rag, working, records):
    from lightrag.utils_pipeline import sidecar_modality_path
    from .ingress import load_verified_bundle,_contained_regular_file
    for record in records:
        if record.get("kind")!="chunk": continue
        name=Path(record.get("source","")).name
        native=await rag.text_chunks.get_by_id(record["chunk_id"])
        if not isinstance(native,dict) or native.get("full_doc_id")!=engine._document_id(name):
            raise engine.LightRagContractError("SDK 文本块所属文档不符")
        refs=(native.get("sidecar") or {}).get("refs") or []
        if not refs: continue
        full=await rag.full_docs.get_by_id(native["full_doc_id"])
        manifest,bundle=load_verified_bundle(working,name)
        raw=__import__("json").loads((bundle/manifest["blocks"]["path"]).read_text(encoding="utf-8"))
        original=[]
        for ref in refs:
            modality={"drawing":"drawings","table":"tables","equation":"equations"}.get(ref.get("type"))
            if modality is None: continue
            sidecar=sidecar_modality_path(full.get("sidecar_location"),modality)
            if not sidecar: raise engine.LightRagContractError("SDK sidecar 来源缺失")
            path=_contained_regular_file(Path(working),Path(sidecar),label="sidecar provenance")
            data=__import__("json").loads(path.read_text(encoding="utf-8"))
            item=data.get(modality,{}).get(ref.get("id"))
            if not isinstance(item,dict): raise engine.LightRagContractError("sidecar 素材ID不符")
            pointer=item.get("self_ref","")
            if not isinstance(pointer,str) or not pointer.startswith("blocks.json#/") or not pointer[13:].isdecimal():
                raise engine.LightRagContractError("sidecar 缺少原文结构指针")
            offset=int(pointer[13:])
            if not 0<=offset<len(raw): raise engine.LightRagContractError("sidecar 原文指针越界")
            block=raw[offset]
            if "heart_block_index" not in block: raise engine.LightRagContractError("sidecar 指针没有Q2块身份")
            original.append({"block_index":block["heart_block_index"],"kind":ref["type"],
                             "asset_id":block.get("heart_asset_id"),"sdk_sidecar_id":ref["id"]})
        record["original_blocks"]=original
    return records


def map_chunks(records, source_map):
    output={}
    for record in records:
        if record.get("kind")!="chunk": continue
        name=Path(record.get("source", "")).name
        if name not in source_map: raise engine.LightRagContractError("LightRAG 返回未登记来源")
        doc=source_map[name];content=record.get("content", "")
        if not isinstance(content,str): raise engine.LightRagContractError("文本块内容无效")
        # 只接纳 chunk 与 Q2 原文的实际连续交集。摘要不参与原文证据。
        spans=list(source_spans(doc["blocks"],content))
        blocks={b["block_index"]:b for b in doc["blocks"]}
        pointer_blocks=set()
        for ref in record.get("original_blocks",[]):
            if ref.get("kind")!="table": continue
            block=blocks.get(ref["block_index"])
            if not block or block["kind"]!="table": raise engine.LightRagContractError("表格指针不对应原始表格")
            text=block_text(block)
            pointer_blocks.add(block["block_index"])
            spans.append({"block_id":block["block_index"],"block_start":0,"block_end":len(text)})
        for span in spans:
            block=blocks[span["block_id"]];original=block_text(block)
            start,end=span["block_start"],span["block_end"]
            text=original[start:end]
            if len(normalized(text))<20: continue
            if block["block_index"] not in pointer_blocks and normalized(text) not in normalized(content): continue
            key=(doc["document_id"],doc["version"],block["block_index"],start,end)
            row=output.setdefault(key,{"document_id":doc["document_id"],"version":doc["version"],
                "source_id":f"{doc['document_id']}:b{block['block_index']}:{start}-{end}",
                "chapter_id":doc["chapter_id"],"section_id":block["section_id"],
                "text":text,"quote":text,"page":None,"image_refs":[],
                "location":{"origin":"lightrag_original_intersection","source":doc["source"],
                    "section":block["section"],"block_start":block["block_index"],"block_end":block["block_index"],
                    "block_char_start":start,"block_char_end":end,"kind":block["kind"],
                    "asset_ids":block.get("image_ids",[])+block.get("formula_ids",[]),
                    "source_spans":[{"block_id":block["block_index"],"block_start":start,"block_end":end,
                                     "text_start":0,"text_end":len(text)}],
                    "sdk_chunk_ids":[],"evidence_status":"candidate_requires_q2_pdf_verification"}})
            chunk_id=record.get("chunk_id")
            if chunk_id and chunk_id not in row["location"]["sdk_chunk_ids"]:
                row["location"]["sdk_chunk_ids"].append(chunk_id)
    return list(output.values())


def as_textbook_chunk(source):
    loc=source["location"]
    return TextbookChunk(source=loc["source"],section=loc["section"],text=source["text"],terms=terms_for(source["text"]),
        kind=loc["kind"],asset_ids=tuple(loc["asset_ids"]),section_id=source["section_id"],
        chunk_id=source["source_id"],chapter_id=source["chapter_id"],page=source["page"],
        block_start=loc["block_start"],block_end=loc["block_end"],source_spans=tuple(loc["source_spans"]))


def rank_sources(query, sources):
    if not sources: return []
    from knowledge.hybrid_retrieval import _reranker_on_device
    from knowledge.local_rag.rerank import _sigmoid
    from knowledge.inference_runtime import configured_device
    backend,model=_reranker_on_device("BAAI/bge-reranker-base",configured_device("RERANK"))
    texts=[source["text"] for source in sources]
    values=list(model.rerank(query,texts,batch_size=4)) if backend=="fastembed" else model.compute_score([[query,t] for t in texts])
    if len(values)!=len(sources) or not all(math.isfinite(float(v)) for v in values):
        raise ValueError("原文重排分数不符合契约")
    # 与 Q2 相同的未经概率校准门槛；失败明确上抛，不回退旧引擎。
    ranked=sorted(zip(values,sources),key=lambda pair:float(pair[0]),reverse=True)
    return [dict(source,score=_sigmoid(float(value))) for value,source in ranked if _sigmoid(float(value))>=.15]


def _graph_context(records, sources):
    output=[]
    for record in records:
        if record["kind"] not in ("entity","relationship"): continue
        chunks=set(record.get("source_id","").split("<SEP>"))
        linked=[source["source_id"] for source in sources if chunks.intersection(source["location"]["sdk_chunk_ids"])]
        output.append(dict(record,evidence_eligible=False,original_source_ids=linked))
    return output


class LightRagBackend:
    def __init__(self, candidate, *, authorized_course_ids, allow_candidate=False):
        path=Path(candidate)
        if path.is_symlink() or bool(getattr(path.lstat(),"st_file_attributes",0)&0x400):
            raise ValueError("候选根不得为 reparse point")
        self.candidate=path.resolve(strict=True)
        self.authorized_course_ids=frozenset(authorized_course_ids)
        self.allow_candidate=bool(allow_candidate)

    def validate(self, course_id):
        if course_id not in self.authorized_course_ids or course_id!=COURSE:
            raise PermissionError("当前请求未授权此教材")
        manifest=json.loads((self.candidate/"input_manifest.json").read_text(encoding="utf-8"))
        state=json.loads((self.candidate/"progress.json").read_text(encoding="utf-8"))
        if not self.allow_candidate: raise RuntimeError("LightRAG 候选索引尚未由集成窗口激活")
        if state["state"]!="candidate_complete" or len(state["chapters"])!=11 or not all(e.get("complete") for e in state["chapters"].values()):
            raise RuntimeError("LightRAG 全书候选索引未完整就绪")
        if manifest["course_id"]!=course_id: raise PermissionError("候选教材身份不符")
        index_files=json.loads((self.candidate/"index_files.json").read_text(encoding="utf-8"))
        if not index_files: raise RuntimeError("候选索引缺少文件签名")
        for relative,sha in index_files.items():
            path=Path(relative)
            if path.is_absolute() or ".." in path.parts: raise RuntimeError("候选索引路径越界")
            from .ingress import _contained_regular_file
            checked=_contained_regular_file(self.candidate,self.candidate/"index"/path,label="native index")
            if digest(checked)!=sha: raise RuntimeError("候选图谱/向量/文本/状态文件身份变化")
        verify(self.candidate/"input",manifest["files"])
        verify(Path(manifest["source_root"]),manifest["files"])
        return manifest

    async def search(self, query, *, course_id, mode="hybrid", limit=6, chapter_id=None, section_id=None, cancellation=None):
        if not isinstance(query,str) or not query.strip() or len(query)>4000: raise ValueError("检索问题无效或过长")
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=40: raise ValueError("结果数必须为1到40")
        if mode not in ("naive","local","global","hybrid","mix"): raise ValueError("检索模式不支持")
        if cancellation is not None and cancellation.is_cancelled(): raise asyncio.CancelledError()
        self.validate(course_id)
        working=self.candidate/"index"
        with write_ownership(self.candidate):
            metrics=Metrics();embedding=await embedding_config(metrics)
            storage.require_compatible_embedding(working,embedding)
            expected=json.loads((self.candidate/"policy.json").read_text(encoding="utf-8"))
            calls=resolve_query_roles(metrics)
            if calls["extract"].config.identity!=expected["extract"]:
                raise RuntimeError("模型配置已变化，需要核对候选策略")
            async def job(bridge):
                rag=engine.build_rag(working,io_bridge=bridge,query_roles=calls,embedding_config=embedding)
                failed=True
                try:
                    await engine.initialize(rag)
                    _,records=await engine.query_with_sources(rag,query,mode)
                    records=await attach_provenance(rag,working,records)
                    failed=False;return records
                finally: await engine.finalize(rag,cancel_pending=failed)
            operation=asyncio.create_task(run_in_worker_loop(job))
            try:
                while not operation.done():
                    if cancellation is not None and cancellation.is_cancelled(): raise asyncio.CancelledError()
                    await asyncio.wait({operation},timeout=.1)
                records=await operation
            finally:
                if not operation.done():
                    operation.cancel();await asyncio.gather(operation,return_exceptions=True)
            self.validate(course_id)
            source_map=json.loads((self.candidate/"source_map.json").read_text(encoding="utf-8"))
            registry=json.loads((self.candidate/"input/pdf_manifest.json").read_text(encoding="utf-8"))
            for name,doc in source_map.items():
                chapter=doc["chapter_id"]
                if not isinstance(chapter,int) or not 1<=chapter<=11 or name!=f"chapter_{chapter:02d}.generated.pdf":
                    raise engine.LightRagContractError("来源映射章节身份错误")
                raw_path=self.candidate/"input/chapters"/f"chapter_{chapter:02d}"/"document.json"
                original=json.loads(raw_path.read_text(encoding="utf-8"))
                pdf=next(r for r in registry if r["chapter_id"]==chapter)
                if digest(raw_path)!=doc["document_sha256"] or doc["source"]!=original["source"] or doc["document_id"]!=pdf["document_id"] or doc["version"]!=pdf["version"]:
                    raise engine.LightRagContractError("来源映射版本不符合冻结原文")
                if len(original["blocks"])!=len(doc["blocks"]): raise engine.LightRagContractError("来源映射块数不符")
                for block,raw in zip(doc["blocks"],original["blocks"]):
                    if any(block.get(k)!=raw.get(k) for k in ("block_index","text","rows","section_id","section","kind","image_ids","formula_ids")):
                        raise engine.LightRagContractError("来源映射不是冻结原文")
            mapped=map_chunks(records,source_map)
            if chapter_id is not None: mapped=[s for s in mapped if s["chapter_id"]==chapter_id]
            if section_id is not None: mapped=[s for s in mapped if s["section_id"]==section_id]
            selected=await asyncio.to_thread(rank_sources,query,mapped)
            self.validate(course_id)
            from .course_input import visual_inventory
            visual_map,_,_=visual_inventory(self.candidate/"input")
            selected_visuals={}
            for record in records:
                if record.get("kind")!="chunk": continue
                doc=source_map[Path(record["source"]).name]
                for ref in record.get("original_blocks",[]):
                    visual=visual_map.get(ref.get("asset_id"))
                    if visual and (chapter_id is None or visual.chapter_id==chapter_id) and (section_id is None or visual.section_id==section_id):
                        selected_visuals[visual.id]=visual.public()|{"document_id":doc["document_id"],"version":doc["version"],
                            "sha256":visual.sha256,"sdk_chunk_id":record["chunk_id"],
                            "evidence_status":"original_image_requires_q2_visual_verification"}
            from knowledge.inference_runtime import runtime_status
            selected=selected[:limit]
            background=_graph_context(records,selected)
            # 图谱摘要只在独立字段给出；reference 和 metadata 不生成证据卡。
            return {"provider":"lightrag","sdk":"1.5.7","mode":mode,"answer":"",
                    "status":"success" if selected else "no_evidence","sources":selected,
                    "graph_context":background,"visuals":list(selected_visuals.values()),"references":[r for r in records if r["kind"]=="reference"],
                    "metadata":[r["metadata"] for r in records if r["kind"]=="query_metadata"],
                    "input_signature":expected["input_signature"],"usage":metrics.public(),"runtime":runtime_status(),
                    "citation_status":"Q2 verification required","rerank_status":"applied" if mapped else "not_needed"}

    def retrieve(self, query, **kwargs):
        result=asyncio.run(self.search(query,**kwargs))
        return [as_textbook_chunk(source) for source in result["sources"]],result


    def prepare_evidence(self, query, result, llm):
        """交给现有 Q2 选择/定位；调用方用返回 bundle.publish 统一正式编号与引用卡。"""
        from knowledge.grounded_citations import choose_evidence,settings
        self.validate(COURSE)
        if result.get("provider")!="lightrag" or result.get("input_signature")!=json.loads(
                (self.candidate/"policy.json").read_text(encoding="utf-8"))["input_signature"]:
            raise ValueError("结果不属于当前候选索引")
        index=settings()
        if index is None: raise RuntimeError("Q2 精确证据核验被关闭，不能发布 LightRAG 教材证据")
        sources=[as_textbook_chunk(source) for source in result["sources"]]
        bundle=choose_evidence(llm,query,sources,index)
        self.validate(COURSE)
        return bundle
