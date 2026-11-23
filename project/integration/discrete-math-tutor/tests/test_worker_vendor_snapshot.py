from hashlib import sha256

from integrations.deeptutor.vendor_snapshot import matches_source


def test_worker_accepts_pinned_patch_and_rejects_other_bytes(tmp_path):
    relative = "learning.py"
    source = tmp_path / relative
    source.write_bytes(b"upstream")
    upstream = sha256(b"upstream").hexdigest()
    manifest = {"files": {relative: upstream}}
    assert matches_source(tmp_path, manifest, relative)
    source.write_bytes(b"approved patch")
    assert not matches_source(tmp_path, manifest, relative)
    patch = tmp_path / "LOCAL_PATCHES/change.patch"
    patch.parent.mkdir()
    patch.write_text("fixture", encoding="utf-8")
    manifest["local_changes"] = [{"path": relative, "upstream_sha256": upstream,
        "local_sha256": sha256(b"approved patch").hexdigest(), "patch": "LOCAL_PATCHES/change.patch"}]
    assert matches_source(tmp_path, manifest, relative)
    source.write_bytes(b"different edit")
    assert not matches_source(tmp_path, manifest, relative)
    source.write_bytes(b"approved patch")
    manifest["local_changes"][0]["upstream_sha256"] = "different baseline"
    assert not matches_source(tmp_path, manifest, relative)
