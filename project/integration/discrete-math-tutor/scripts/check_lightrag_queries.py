"""全书真实检索和Q2证据协议检查；页面与正式接线不在本脚本范围。"""
import argparse,asyncio,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("candidate",type=Path)
    parser.add_argument("--env-file",type=Path,required=True)
    args=parser.parse_args();candidate=args.candidate.resolve(strict=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file,override=False)
    os.environ.setdefault("OMP_NUM_THREADS","2");os.environ.setdefault("MKL_NUM_THREADS","2")
    os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
    from knowledge import course_config
    course_config.PSYCHOLOGY_DIR=candidate/"input"
    from knowledge import pdf_reader
    pdf_reader.CROPS=candidate/"validation_crops"
    from knowledge.lightrag.retrieval import LightRagBackend
    from knowledge.lightrag.course_input import COURSE
    from knowledge.lightrag.file_io import atomic_write_json
    from knowledge.lightrag.config import Metrics,HostModel,build_llm_model_func
    from knowledge.lightrag.pipeline import _resource
    from knowledge.grounding_text import normalized
    from llm.client import LLMClient,extract_json
    backend=LightRagBackend(candidate,authorized_course_ids={COURSE},allow_candidate=True)
    report={"scope":"independent backend + real SDK + real model keyword/evidence selection",
            "page_acceptance":"not run; integration window owns public wiring","resource_start":_resource(), "case_scope":{"figure":"原图身份检索；pending不等于视觉审核", "formula":"公式相关原文检索；不含OMML逐式核验", "chapter_overview":"全节素材覆盖；不生成正式概述"},"cases":[]}
    cases=[
        ("concept","什么是自变量",["自变量"],None),
        ("synonym","操作定义是什么意思",["操作性定义"],None),
        ("comparison","被试内设计和被试间设计有什么区别",["被试内","被试间"],None),
        ("cross_chapter","第一章的实验程序和第二章的自变量控制有哪些联系",[],{1,2}),
        ("chapter_overview","第二章有哪些实验变量与控制方法",["变量"],{2}),
        ("figure","图1-1液体守恒实验说明了什么",[],None),
        ("formula","差别感觉阈限DL公式中PSE是什么",["PSE"],{7}),
        ("no_basis","火星表面玄武岩的晶体结构",[],set()),
    ]
    for name,question,terms,chapters in cases:
        started=time.monotonic()
        try:
            chunks,result=backend.retrieve(question,course_id=COURSE,limit=10,
                chapter_id=2 if name=="chapter_overview" else None)
            text=normalized("\n".join(s["text"] for s in result["sources"]))
            actual={s["chapter_id"] for s in result["sources"]}
            ok=all(normalized(t) in text for t in terms)
            if chapters is not None:ok=ok and ((not actual) if not chapters else chapters.issubset(actual))
            if name=="figure":ok=any("图1-1" in str(v.get("label","")) for v in result["visuals"])
            assert not result["answer"]
            assert all(not context["evidence_eligible"] for context in result["graph_context"])
            source_ids={s["source_id"] for s in result["sources"]}
            assert all(set(c["original_source_ids"])<=source_ids for c in result["graph_context"])
            coverage=None
            if name=="chapter_overview":
                doc=json.loads((candidate/"input/chapters/chapter_02/document.json").read_text(encoding="utf-8"))
                expected={b.get("section_id") for b in doc["blocks"] if b.get("section_id")}
                covered={s["section_id"] for s in result["sources"] if s.get("section_id")}
                ok=ok and not (expected-covered)
                coverage={"retrieval_covers_all_sections":not (expected-covered),"expected_sections":sorted(expected),"retrieved_sections":sorted(covered),
                          "missing_sections":sorted(expected-covered),"complete_overview":False,
                          "scope":"检索素材检查；全章概述必须由Q2/Q3按全部节生成并核验"}
            atomic_write_json(candidate/("query-"+name+".json"),result)
            report["cases"].append({"case":name,"query":question,"passed":ok,"mode":result["mode"],
                "sources":len(result["sources"]),"chapters":sorted(actual),"visuals":result["visuals"],
                "usage":result["usage"],"sdk_metadata":result["metadata"],"resource_after":_resource(),"coverage":coverage,"seconds":time.monotonic()-started})
        except Exception as exc:
            report["cases"].append({"case":name,"query":question,"passed":False,"error_type":type(exc).__name__,
                "error":str(exc),"seconds":time.monotonic()-started})
        atomic_write_json(candidate/"query_validation.json",report)
    # 其余模式至少真实调用一次；不以 mode 字段存在代替实际运行。
    report["modes"]=[]
    for mode in ("naive","local","global","mix"):
        started=time.monotonic()
        try:
            result=asyncio.run(backend.search("什么是自变量",course_id=COURSE,mode=mode,limit=6))
            report["modes"].append({"mode":mode,"passed":bool(result["sources"]),"sources":len(result["sources"]),
                "usage":result["usage"],"sdk_metadata":result["metadata"],"seconds":time.monotonic()-started})
        except Exception as exc:report["modes"].append({"mode":mode,"passed":False,"error_type":type(exc).__name__,"error":str(exc)})
    atomic_write_json(candidate/"query_validation.json",report)
    report["q3_tool"]={"status":"not_run","reason":"等待集成窗口确认稳定基线及正式工具接线"}
    # 使用真实Q2模块完成证据选择、PDF定位和同一EvidenceBundle发布；不生成另一个正式答案。
    evidence_metrics=Metrics(candidate/"evidence_usage.json")
    class EvidenceLLM:
        def chat_json(self,messages,**kwargs):
            text=asyncio.run(build_llm_model_func(llm_config=HostModel(LLMClient(),evidence_metrics,"q2_evidence_selection"))(
                messages=messages,response_format={"type":"json_object"}))
            return extract_json(text)
    try:
        retrieval=json.loads((candidate/"query-concept.json").read_text(encoding="utf-8"))
        bundle=backend.prepare_evidence("什么是自变量",retrieval,EvidenceLLM())
        body,published_sources,refs=bundle.publish(bundle.sources[0].text+" [1]")
        assert len(published_sources)==1
        assert refs and len(refs)==1 and refs[0]["source_index"]==0 and "[1]" in body
        evidence=refs[0]["evidence"]
        assert evidence["document_version"] and evidence["quote"]
        assert evidence["verification"]=="source_verified"
        assert evidence["location_status"]=="exact" and evidence["page"] and evidence["selections"],"Q2未返回精确页码/高亮"
        assert normalized(evidence["quote"]) in normalized("\n".join(row["text"] for row in evidence["selections"]))
        crop_checks=[]
        for selection in evidence["selections"]:
            assert selection["document_id"]==evidence["document_id"] and selection["version"]==evidence["document_version"]
            assert selection["rects"] and selection["image_refs"]
            for image in selection["image_refs"]:
                path=pdf_reader.crop_path(image["id"])
                assert path is not None and path.is_file(),"Q2裁图身份/版本校验失败"
                crop_checks.append({"id":image["id"],"path":str(path)})
        backend.validate(COURSE)
        report["q2_evidence"]={"passed":True,"mode":"exact original quote publication assertion; not a generated formal answer",
            "reference":refs[0],"body":body,"crop_checks":crop_checks,"usage":evidence_metrics.public()}
    except Exception as exc:
        report["q2_evidence"]={"passed":False,"error_type":type(exc).__name__,"error":str(exc),"usage":evidence_metrics.public()}
    report["passed"]=all(c["passed"] for c in report["cases"]+report["modes"]+[report["q2_evidence"]])
    report["resource_end"]=_resource()
    atomic_write_json(candidate/"query_validation.json",report)
    print(json.dumps({"passed":report["passed"],"cases":[(c["case"],c["passed"]) for c in report["cases"]]},ensure_ascii=False))
    return 0 if report["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
