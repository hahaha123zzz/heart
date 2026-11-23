"""核对原生接线依赖与版本清单中的实际交付源码。"""
import hashlib


def matches_source(root, pin, relative):
    upstream = pin["files"][relative]
    local = [entry for entry in pin.get("local_changes", []) if entry.get("path") == relative]
    if local:
        if len(local) != 1 or local[0].get("upstream_sha256") != upstream:
            return False
        patch = local[0].get("patch", "")
        if not patch.startswith("LOCAL_PATCHES/") or not (root / patch).resolve().is_relative_to(root / "LOCAL_PATCHES") or not (root / patch).is_file():
            return False
        expected = local[0].get("local_sha256")
    else:
        expected = upstream
    return hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
