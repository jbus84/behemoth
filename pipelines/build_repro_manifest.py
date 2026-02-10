#!/usr/bin/env python3
"""
Build a reproducibility manifest for the MOM strategy.

Outputs:
- data/analysis/repro_manifest.json
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path.append(os.path.join(os.getcwd(), "src"))
import behemoth.config as cfg

OUT_PATH = "data/analysis/repro_manifest.json"
DEFAULT_FILES = [
    "data/meta_model/events_m5_8yr_v3_mom.csv",
    "data/meta_model/events_m15_8yr_v3_mom.csv",
]


@dataclass
class FileMeta:
    path: str
    sha256: str | None
    size_bytes: int | None
    mtime_utc: str | None


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_file_meta(paths: Iterable[str]) -> list[FileMeta]:
    metas = []
    for p in paths:
        if not os.path.exists(p):
            metas.append(FileMeta(path=p, sha256=None, size_bytes=None, mtime_utc=None))
            continue
        stat = os.stat(p)
        metas.append(
            FileMeta(
                path=p,
                sha256=_sha256(p),
                size_bytes=int(stat.st_size),
                mtime_utc=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            )
        )
    return metas


def _git_cmd(args: list[str]) -> str | None:
    try:
        out = subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return None


def git_info() -> dict:
    return {
        "commit": _git_cmd(["rev-parse", "HEAD"]),
        "branch": _git_cmd(["rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty": bool(_git_cmd(["status", "--porcelain"])),
    }


def config_snapshot() -> dict:
    return {
        "Z_ENTRY_MOM": cfg.Z_ENTRY_MOM,
        "Z_ENTRY_REV": cfg.Z_ENTRY_REV,
        "Z_STOP": cfg.Z_STOP,
        "MIN_GAP_BARS": cfg.MIN_GAP_BARS,
        "LOOKBACK_BARS": cfg.LOOKBACK_BARS,
        "ACTIVE_LEG_LOW": cfg.ACTIVE_LEG_LOW,
        "ACTIVE_LEG_HIGH": cfg.ACTIVE_LEG_HIGH,
    }


def build_manifest(paths: Iterable[str] = DEFAULT_FILES, include_git: bool = True) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "config": config_snapshot(),
        "files": [asdict(m) for m in collect_file_meta(paths)],
        "git": git_info() if include_git else None,
    }


def main() -> None:  # pragma: no cover
    os.makedirs(Path(OUT_PATH).parent, exist_ok=True)
    manifest = build_manifest()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
