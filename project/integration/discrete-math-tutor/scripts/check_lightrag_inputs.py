"""验证全部11章实际转换与源文件身份；不调用模型。"""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from knowledge.lightrag.course_input import verify,convert,visual_inventory
from knowledge.lightrag.ingress import load_verified_bundle
from knowledge.lightrag.sidecar import build_ir
from knowledge.lightrag.file_io import atomic_write_json

def check(candidate):
    candidate=Path(candidate);manifest=json.loads((candidate/"input_manifest.json").read_text(encoding="utf-8"))
    verify(candidate/"input",manifest["files"]);verify(Path(manifest["source_root"]),manifest["files"])
    visuals,gaps,stats=visual_inventory(candidate/"input")
    chapters=[];used=set();started=time.monotonic()
    for chapter in range(1,12):
        source,parsed,mapping=convert(candidate/"input",chapter,visual_map=visuals)
        frozen,bundle=load_verified_bundle(candidate/"index",source.name)
        ir=build_ir(frozen,bundle)
        raw=json.loads((bundle/frozen["blocks"]["path"]).read_text(encoding="utf-8"))
        expected_text=[b["text"] for b in mapping["blocks"] if b["text"].strip()]
        actual_text=[b["text"] for b in raw if b.get("type")=="text"]
        assert actual_text==expected_text, f"第{chapter}章原文发生变化"
        tables=sum(b["kind"]=="table" for b in mapping["blocks"])
        assert sum(len(block.tables) for block in ir.blocks)==tables
        raw_images=[b for b in raw if b.get("type")=="image"]
        for image in raw_images:
            assert image["heart_asset_id"] in visuals
            assert image["review_status"]==visuals[image["heart_asset_id"]].review_status
            used.add(image["heart_asset_id"])
        assert all(image["heart_asset_id"] not in {g["visual_id"] for g in gaps} for image in raw_images)
        chapters.append({"chapter_id":chapter,"blocks":len(mapping["blocks"]),"text_blocks":len(expected_text),
            "tables":tables,"image_occurrences":len(raw_images),"sidecar_blocks":len(ir.blocks),
            "omml_objects":len(mapping["omml_objects"]),"document_version":mapping["version"],
            "document_sha256":mapping["document_sha256"],"original_text_preserved":True})
    assert len(chapters)==11
    report={"input_signature":manifest["input_signature"],"chapters":chapters,"visuals":stats,
        "excluded_visuals":gaps,"unique_indexed_visuals":len(used),"unmapped_valid_visuals":sorted(set(visuals)-used),
        "multimodal_complete":False,"multimodal_limits":["179项有效原图仍为pending审核","44项已确认装饰栏头按Q2记录排除", "原始OMML保留，尚未逐式核对PDF"],
        "checks_passed":True,"elapsed_seconds":time.monotonic()-started}
    atomic_write_json(candidate/"input_validation.json",report);return report
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("candidate",type=Path);args=parser.parse_args()
    report=check(args.candidate);print(json.dumps({"chapters":len(report["chapters"]),"checks_passed":report["checks_passed"],
        "unique_indexed_visuals":report["unique_indexed_visuals"],"unmapped_valid_visuals":report["unmapped_valid_visuals"]},ensure_ascii=False))
