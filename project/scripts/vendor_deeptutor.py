"""迁入固定提交的完整源码，保留已核查修复，并校验文件完整性。"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


COMMIT = "6cf793bd868ba5ecbe64722936d4be8fab5a01df"
DESTINATION = Path(__file__).resolve().parents[1] / "vendor" / "DeepTutor"
MANIFEST = "UPSTREAM_SNAPSHOT.json"
LOCAL_FIX = "deeptutor/services/llm/factory.py"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
        raise ValueError(f"归档路径无效：{name}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"归档路径超出目标：{name}")
    return path


def verify(root: Path = DESTINATION) -> dict:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("commit") != COMMIT or not manifest.get("files"):
        raise ValueError("源码清单提交或文件集合无效")
    for name, expected in manifest["files"].items():
        path = safe_path(root, name)
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError(f"源码缺失或已修改：{name}")
    return {"commit": COMMIT, "verified_files": len(manifest["files"]),
            "local_changes": manifest["local_changes"]}


def snapshot(source: Path, destination: Path = DESTINATION) -> dict:
    if destination.exists():
        raise FileExistsError("目标已存在；请使用 --verify 校验，不自动覆盖")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip() != COMMIT:
        raise ValueError("源项目提交与调研固定版本不同")
    archive = subprocess.check_output(["git", "archive", "--format=tar", COMMIT], cwd=source)
    stage = destination.with_name(destination.name + ".importing")
    if stage.exists():
        raise FileExistsError(f"存在未完成的迁入目录：{stage}")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        members = tar.getmembers()
        for member in members:
            safe_path(stage, member.name)
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"归档不允许链接或特殊文件：{member.name}")
        stage.mkdir(parents=True)
        files = {}
        for member in members:
            if not member.isfile():
                continue
            path = safe_path(stage, member.name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as stream:
                data = stream.read()
            path.write_bytes(data)
            files[member.name] = digest(data)
    changes = []
    local = (source / LOCAL_FIX).read_bytes()
    upstream = (stage / LOCAL_FIX).read_bytes()
    if local != upstream:
        patch = subprocess.check_output(["git", "diff", "--", LOCAL_FIX], cwd=source)
        expected = (b'    if not hasattr(config, "get_api_key"):\n'
                    b'        # A provider-runtime ResolvedLLMConfig lacks the LLM service shape\n'
                    b'        # (get_api_key/temperature/max_tokens) that the isolated provider\n'
                    b"        # builder expects; convert it once, preserving the caller's value.\n"
                    b'        from deeptutor.services.model_selection.runtime import llm_config_from_resolved\n\n'
                    b'        config = llm_config_from_resolved(config)\n')
        if local.replace(b"\r\n", b"\n").replace(expected, b"", 1) != upstream.replace(b"\r\n", b"\n"):
            raise ValueError("本地 LLM 修改超出已核查修复；原样保留暂存目录供检查")
        (stage / LOCAL_FIX).write_bytes(local)
        files[LOCAL_FIX] = digest(local)
        patch_name = "LOCAL_PATCHES/llm-config-adapter.patch"
        patch_path = stage / patch_name
        patch_path.parent.mkdir()
        patch_path.write_bytes(patch)
        files[patch_name] = digest(patch)
        changes.append({"path": LOCAL_FIX, "upstream_sha256": digest(upstream),
                        "local_sha256": digest(local), "patch": patch_name,
                        "reason": "将 ResolvedLLMConfig 转换为独立 provider 需要的 LLMConfig"})
    manifest = {"commit": COMMIT, "source": "HKUDS/DeepTutor", "snapshot_date": "2026-10-18",
                "scope": "完整 Git 跟踪源码及资源，不含工作区运行数据/私密配置",
                "local_changes": changes, "files": dict(sorted(files.items()))}
    (stage / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stage.rename(destination)
    return verify(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        result = verify()
    elif args.source is not None:
        result = snapshot(args.source)
    else:
        parser.error("首次迁入需提供本地源项目路径；已有副本使用 --verify")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
