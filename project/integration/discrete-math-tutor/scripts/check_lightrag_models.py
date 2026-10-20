"""固定输入上的JSON/图像契约实测；凭据仅从现有环境读取。"""
import argparse,asyncio,base64,json,sys,mimetypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("source",type=Path)
    parser.add_argument("--env-file",type=Path,required=True)
    parser.add_argument("--report",type=Path,default=ROOT/".runtime/lightrag-model-check.json")
    args=parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(args.env_file,override=False)
    from knowledge.lightrag.course_input import declared_snapshot,verify,visual_inventory
    from knowledge.lightrag.config import Metrics,HostModel,build_llm_model_func,build_vision_model_func
    from knowledge.lightrag.file_io import atomic_write_json
    from knowledge.lightrag.engine import _require_exact_version
    from llm.client import LLMClient,extract_json
    source=args.source.resolve(strict=True);declaration=declared_snapshot(source)
    assert declaration,"模型检查必须使用Q2已声明的冻结输入"
    _require_exact_version()
    visuals,_,_=visual_inventory(source);visual=next(iter(visuals.values()))
    metrics=Metrics();client=LLMClient();extract=HostModel(client,metrics,"extract")
    vision=HostModel(LLMClient(model=client.vision_model),metrics,"vlm")
    async def run():
        text=await build_llm_model_func(llm_config=extract)('Return a JSON object with ready=true.',response_format={"type":"json_object"})
        assert extract_json(text).get("ready") is True,"结构化JSON契约不符"
        payload={"base64":base64.b64encode(visual.path.read_bytes()).decode(),"mime_type":mimetypes.guess_type(visual.path.name)[0] or "image/png"}
        text=await build_vision_model_func(llm_config=vision)(prompt='Describe visible shapes briefly in a JSON object with a summary string.',image_inputs=[payload],response_format={"type":"json_object"})
        assert isinstance(extract_json(text).get("summary"),str) and extract_json(text)["summary"].strip(),"图像输入/JSON契约不符"
    asyncio.run(run())
    report={"passed":True,"extract":extract.identity,"vlm":vision.identity,"input_signature":declaration["snapshot_id"],
            "visual_id":visual.id,"review_status":visual.review_status,"scope":"API contract only; not teacher visual review","usage":metrics.public()}
    atomic_write_json(args.report,report)
    print(json.dumps({"passed":True,"extract":extract.identity,"usage":metrics.public()},ensure_ascii=False))
    return 0
if __name__=="__main__":raise SystemExit(main())
