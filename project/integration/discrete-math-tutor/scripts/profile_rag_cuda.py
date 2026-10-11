"""用 ONNX 算子事件验证 reranker 实际在 GPU 运算。"""
import json
import sys
from datetime import datetime, timezone
import onnxruntime as ort
from collections import Counter
from pathlib import Path
from fastembed.rerank.cross_encoder import TextCrossEncoder
from knowledge.inference_runtime import prepare_onnx, verify_device

if __name__ == "__main__":
    prepare_onnx("cuda")
    m = TextCrossEncoder("BAAI/bge-reranker-base", lazy_load=True, cuda=True, threads=4)
    inner = m.model
    inner._load_onnx_model(inner._model_dir, inner.model_description.model_file,
        threads=4, cuda=False)
    options = ort.SessionOptions()
    options.enable_profiling = True
    options.profile_file_prefix = "artifacts/reranker-cuda-profile"
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 4
    inner.model = ort.InferenceSession(str(inner._model_dir / inner.model_description.model_file),
        sess_options=options, providers=["CUDAExecutionProvider"])
    verify_device(m, "cuda")
    scores = list(m.rerank("合取什么时候为真？", ["两个命题都为真时合取为真。"], batch_size=1))
    profile = Path(inner.model.end_profiling())
    events = json.loads(profile.read_text(encoding="utf-8"))
    kernels = [e for e in events if e.get("cat") == "Node" and e.get("args", {}).get("provider")]
    counts = Counter(e["args"]["provider"] for e in kernels)
    operators = Counter(e["args"].get("op_name", "") for e in kernels if e["args"]["provider"] == "CUDAExecutionProvider")
    result = {"scores": scores, "providers": inner.model.get_providers(), "node_events": dict(counts), "cuda_operators": dict(operators), "profile": str(profile)}
    if not counts["CUDAExecutionProvider"]:
        raise RuntimeError("No CUDA node events found")
    Path("artifacts/reranker-cuda-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    if Path(sys.prefix).resolve() == (root / ".venv-gpu").resolve():
        (root / ".venv-gpu/gpu-verified.json").write_text(json.dumps({
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "model": "BAAI/bge-reranker-base", "onnxruntime": ort.__version__,
            "cuda_node_events": counts["CUDAExecutionProvider"]}), encoding="utf-8")
    print(json.dumps(result), flush=True)
