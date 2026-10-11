"""显式选择小模型设备，并验证 ONNX 会话实际启用了 CUDA。"""
from __future__ import annotations
import os
from pathlib import Path

def configured_device(component: str) -> str:
    device = os.environ.get(f"RAG_{component}_DEVICE", "cpu").strip().lower()
    if device not in {"cpu", "cuda"}:
        raise ValueError(f"RAG_{component}_DEVICE must be cpu or cuda")
    return device

def prepare_onnx(device: str) -> dict:
    if device == "cpu":
        return {"cuda": False, "providers": ["CPUExecutionProvider"]}
    # 部分桌面启动环境没有 APPDATA，显式目录确保 JIT 缓存可跨进程复用。
    # 尊重用户已有 CUDA_CACHE_PATH 与缓存禁用设置。
    cache_path = os.environ.get("CUDA_CACHE_PATH")
    if not cache_path:
        cache_path = str(Path(__file__).resolve().parents[1] / ".cache" / "cuda")
        Path(cache_path).mkdir(parents=True, exist_ok=True)
        os.environ["CUDA_CACHE_PATH"] = cache_path
    import onnxruntime as ort
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("CUDAExecutionProvider unavailable; use the GPU Python environment")
    # 从 NVIDIA wheel 加载 DLL，不修改系统 PATH 或驱动。
    ort.preload_dlls(directory="")
    return {"cuda": True}

def session_providers(model) -> list[str]:
    return list(model.model.model.get_providers())

def verify_device(model, device: str) -> None:
    if device == "cuda" and "CUDAExecutionProvider" not in session_providers(model):
        raise RuntimeError("CUDA session initialization failed; refusing silent CPU execution")

_sessions: dict = {}

def record_session(component: str, model, device: str) -> None:
    _sessions[component] = {"device": device, "providers": session_providers(model)}

def runtime_status() -> dict:
    return {"configured": {"reranker": configured_device("RERANK"),
                           "embedding": configured_device("EMBED")},
            "sessions": dict(_sessions),
            "cuda_cache_path": os.environ.get("CUDA_CACHE_PATH")}
