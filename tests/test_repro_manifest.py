import hashlib

import build_repro_manifest as bm


def test_collect_file_meta(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("abc", encoding="utf-8")
    meta = bm.collect_file_meta([str(path)])[0]
    assert meta.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert meta.size_bytes == 3
    assert meta.mtime_utc is not None


def test_build_manifest_no_git(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("x", encoding="utf-8")
    manifest = bm.build_manifest([str(path)], include_git=False)
    assert "generated_at" in manifest
    assert "config" in manifest
    assert manifest["git"] is None
    files = manifest["files"]
    assert len(files) == 1
    assert files[0]["path"] == str(path)
