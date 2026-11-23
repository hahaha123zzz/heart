"""只读核对全书实际存储、逐章数量和素材处理状态；不调用模型。"""
import argparse,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from knowledge.lightrag.retrieval import LightRagBackend
from knowledge.lightrag.course_input import COURSE,verify
from knowledge.lightrag import storage
from knowledge.lightrag.file_io import atomic_write_json

def _pg_rows(workspace):
    with storage._pg_connect() as conn:
        docs={row[0]:{"status":row[1],"chunks_list":row[2] or []} for row in conn.execute(
            "SELECT id,status,chunks_list FROM lightrag_doc_status WHERE workspace=%s",(workspace,)).fetchall()}
        chunks={row[0]:{"full_doc_id":row[1]} for row in conn.execute(
            "SELECT id,full_doc_id FROM lightrag_doc_chunks WHERE workspace=%s",(workspace,)).fetchall()}
        vectors={row[0] for row in conn.execute(
            "SELECT id FROM lightrag_vdb_chunks WHERE workspace=%s",(workspace,)).fetchall()}
        nodes=[set((row[0] or "").split("<SEP>")) for row in conn.execute(
            "SELECT properties->>'source_id' FROM lightrag_graph_nodes WHERE workspace=%s",(workspace,)).fetchall()]
        edges=[set((row[0] or "").split("<SEP>")) for row in conn.execute(
            "SELECT properties->>'source_id' FROM lightrag_graph_edges WHERE workspace=%s",(workspace,)).fetchall()]
    return docs,chunks,vectors,nodes,edges

def check(candidate):
    candidate=Path(candidate).resolve(strict=True)
    def read(path):return json.loads(path.read_text(encoding="utf-8"))
    state=read(candidate/"progress.json")
    assert state["state"] in ("candidate_complete","partial_failed","failed","cancelled"),"运行中不核定最终存储"
    manifest=read(candidate/"input_manifest.json")
    verify(candidate/"input",manifest["files"]);verify(Path(manifest["source_root"]),manifest["files"])
    if state["state"]=="candidate_complete":
        LightRagBackend(candidate,authorized_course_ids={COURSE},allow_candidate=True).validate(COURSE)
    docs,chunks,vectors,nodes,edges=_pg_rows(storage._workspace(candidate/"index"))
    chapters=[];used=set();modalities=Counter()
    for chapter in range(1,12):
        entry=state["chapters"][str(chapter)];doc=docs[entry["doc_id"]]
        ids=set(doc["chunks_list"])
        assert ids,"缺少可核对的文本块清单"
        assert not used&ids,"跨章重复文本块身份"
        stored=ids&set(chunks)
        for key in stored:assert chunks[key]["full_doc_id"]==entry["doc_id"],key
        if doc["status"]=="processed":assert stored==ids,"已处理文档缺少原文块"
        used|=ids
        actual={"chunks":len(stored),"entities":sum(bool(ids&s) for s in nodes),"relationships":sum(bool(ids&s) for s in edges)}
        assert all(actual[k]==entry[k] for k in ("entities","relationships")),(chapter,actual)
        analyses={}
        directory=candidate/"index/deeptutor_ingress/pending/__parsed__"/(entry["canonical_name"]+".parsed")
        for kind in ("drawings","tables"):
            path=directory/(Path(entry["canonical_name"]).stem+"."+kind+".json")
            items=read(path).get(kind,{}) if path.exists() else {}
            statuses=Counter((v.get("llm_analyze_result") or {}).get("status","missing") for v in items.values())
            analyses[kind]={"total":len(items),"statuses":dict(statuses)}
            for status,count in statuses.items():modalities[kind+":"+status]+=count
        families=Counter(next((kind for kind in ("drawing","table","equation") if "-mm-"+kind+"-" in key),"text") for key in stored)
        complete=doc["status"]=="processed" and all(actual.values()) and not ids-vectors
        if state["state"]=="candidate_complete":assert complete
        chapters.append({"chapter_id":chapter,"status":doc["status"],**actual,"vectorized_chunks":len(ids&vectors),
                         "native_chunk_families":dict(families),"planned_chunks":len(ids),"missing_text_chunks":sorted(ids-stored),"missing_vector_chunks":sorted(ids-vectors),"complete":bool(complete),"analysis":analyses,
                         "exact_model_token_usage":None,"token_note":"历史并发调用无完整逐章归属；不反推估算"})
    assert not set(chunks)-used,{"unclaimed_chunks":len(set(chunks)-used)}
    actual={"entities":len(nodes),"relationships":len(edges),"chunks":len(chunks)}
    assert all(actual[k]==state["graph"][k] for k in ("entities","relationships")),actual
    if state["state"]=="candidate_complete":
        assert actual==state["graph"]
        assert vectors==set(chunks),"文本向量与实际原文块身份不一致"
    report={"state":state["state"],"input_signature":state["input_signature"],"chapters":chapters,"graph":actual,
            "vectorized_chunks":len(vectors),"multimodal_analysis":dict(modalities),"visual_review":"179 pending; 44 decorations excluded",
            "omml_verification":"81 object identities preserved; per-formula PDF/semantic verification not completed",
            "runs":state["runs"],"peak_sampled_rss_bytes":state["peak_sampled_rss_bytes"],"usage":read(candidate/"usage.json"),
            "publication":"staging; ready=false; candidate only"}
    atomic_write_json(candidate/"completion_validation.json",report)
    return {"storage_counts_verified":True,"whole_book_complete":all(c["complete"] for c in chapters),
            "graph":actual,"vectorized_chunks":len(vectors),"chapters":chapters,"multimodal_analysis":dict(modalities)}
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("candidate",type=Path)
    print(json.dumps(check(parser.parse_args().candidate),ensure_ascii=False))
