#!/usr/bin/env python3
"""Build analysis docs catalog and manifest."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


CORE_REPORTS = {
    "analysis/data_reliability_report.md",
    "analysis/operator_action_report.md",
    "analysis/oco_leakage_integrity_report.md",
    "analysis/oco_execution_risk_prelive_report.md",
    "analysis/oco_execution_monte_carlo_report.md",
    "analysis/oco_execution_monte_carlo_validation_report.md",
    "analysis/oco_logical_audit_report.md",
    "analysis/oco_edge_clarity_report.md",
    "analysis/oco_docs_contract_report.md",
    "analysis/run_delta_dashboard.md",
    "analysis/taxonomy_rules.md",
}

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")

STAGE_KEYWORDS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("data_reliability",)),
    (2, ("mining", "opportunity_mining")),
    (3, ("monthly_wfo", "_wfo_")),
    (4, ("stop_limit", "execution_risk")),
    (5, ("reduced_core",)),
    (6, ("tick_exact",)),
    (7, ("logical_audit",)),
    (8, ("robustness", "remediation_metric_decomposition")),
    (9, ("governance", "live_governance")),
    (10, ("risk", "checklist")),
    (11, ("execution_monte_carlo",)),
]

LEGACY_KEYWORDS: tuple[str, ...] = (
    "close_path_contracts",
    "cluster_earlywarning",
    "kf_directional",
    "mom_loss_limiter",
    "m5_mom_m15_momrev",
    "stable_pairs_whitelist",
)


@dataclass(frozen=True)
class ClassifiedDoc:
    doc_path: str
    title: str
    symbol: str
    stage_id: int | None
    group: str
    is_core: bool
    is_archive: bool
    mtime_utc: str


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _human_title(path: Path) -> str:
    s = path.stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(w.capitalize() for w in s.split())


def _infer_symbol(name_l: str) -> str:
    for sym in SYMBOLS:
        tok = sym.lower()
        if name_l.startswith(tok + "_") or f"_{tok}_" in name_l or tok in name_l:
            return sym
    return "ALL"


def _infer_stage(name_l: str) -> int | None:
    for stage_id, keys in STAGE_KEYWORDS:
        if any(k in name_l for k in keys):
            return stage_id
    return None


def _classify_doc(path: Path, docs_root: Path) -> ClassifiedDoc:
    rel = path.relative_to(docs_root).as_posix()
    name_l = path.name.lower()
    sym = _infer_symbol(name_l)
    stage_id = _infer_stage(name_l)
    is_archive = rel.startswith("archive/")
    is_core = rel in CORE_REPORTS
    if is_archive:
        group = "archive"
    elif is_core:
        group = "core"
    elif sym != "ALL":
        group = "symbol"
    elif stage_id is not None:
        group = "stage"
    elif any(k in name_l for k in LEGACY_KEYWORDS):
        group = "legacy"
    else:
        group = "unclassified"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ClassifiedDoc(
        doc_path=rel,
        title=_human_title(path),
        symbol=sym,
        stage_id=stage_id,
        group=group,
        is_core=is_core,
        is_archive=is_archive,
        mtime_utc=mtime,
    )


def _render_index(manifest: pd.DataFrame, *, docs_root: Path) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append("# Analysis Catalog")
    lines.append("")
    lines.append(f"- generated_at_utc: `{now}`")
    lines.append(f"- manifest_csv: `analysis/catalog_manifest.csv`")
    lines.append(f"- gaps_report: `analysis/catalog_gaps_report.md`")
    lines.append("")

    lines.append("## Core Reports")
    core = manifest[manifest["group"] == "core"].copy()
    if core.empty:
        lines.append("_empty_")
    else:
        core = core.sort_values("doc_path")
        for _, r in core.iterrows():
            lines.append(f"- [{r['title']}]({r['doc_path'].replace('analysis/', '')})")
    lines.append("")

    lines.append("## Symbol Reports")
    sym = manifest[manifest["group"] == "symbol"].copy()
    if sym.empty:
        lines.append("_empty_")
    else:
        for s in SYMBOLS:
            lines.append(f"### {s}")
            g = sym[sym["symbol"] == s].copy().sort_values("doc_path")
            if g.empty:
                lines.append("_empty_")
                continue
            for _, r in g.iterrows():
                lines.append(f"- [{r['title']}]({r['doc_path'].replace('analysis/', '')})")
    lines.append("")

    lines.append("## Stage-Tagged Reports")
    stage = manifest[manifest["stage_id"].notna() & (~manifest["is_archive"].astype(bool))].copy()
    if stage.empty:
        lines.append("_empty_")
    else:
        stage["stage_id"] = pd.to_numeric(stage["stage_id"], errors="coerce").astype("Int64")
        agg = (
            stage.groupby("stage_id", as_index=False)
            .agg(report_count=("doc_path", "count"))
            .sort_values("stage_id")
        )
        lines.append(_table(agg))
    lines.append("")

    lines.append("## Legacy Reports")
    legacy = manifest[manifest["group"] == "legacy"].copy().sort_values("doc_path")
    if legacy.empty:
        lines.append("_empty_")
    else:
        for _, r in legacy.iterrows():
            lines.append(f"- [{r['title']}]({r['doc_path'].replace('analysis/', '')})")
    lines.append("")

    lines.append("## Unclassified Reports")
    unclassified = manifest[manifest["group"] == "unclassified"].copy().sort_values("doc_path")
    if unclassified.empty:
        lines.append("_empty_")
    else:
        for _, r in unclassified.iterrows():
            lines.append(f"- [{r['title']}]({r['doc_path'].replace('analysis/', '')})")
    lines.append("")

    lines.append("## Archive Links")
    arch = manifest[manifest["is_archive"].astype(bool)].copy().sort_values("doc_path")
    if arch.empty:
        lines.append("_empty_")
    else:
        for _, r in arch.iterrows():
            lines.append(f"- [{r['title']}](../{r['doc_path']})")
    return "\n".join(lines)


def _render_gaps(manifest: pd.DataFrame, *, docs_root: Path) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append("# Analysis Catalog Gaps")
    lines.append("")
    lines.append(f"- generated_at_utc: `{now}`")
    lines.append("")

    have = set(manifest["doc_path"].astype(str).tolist())
    missing_core = sorted([p for p in CORE_REPORTS if p not in have])
    lines.append("## Missing Core Reports")
    lines.append("_empty_" if not missing_core else "\n".join(f"- `{x}`" for x in missing_core))
    lines.append("")

    unclassified = manifest[manifest["group"].astype(str) == "unclassified"].copy()
    lines.append("## Unclassified Reports")
    if unclassified.empty:
        lines.append("_empty_")
    else:
        lines.append(_table(unclassified[["doc_path", "group", "symbol"]].sort_values("doc_path")))
    lines.append("")

    lines.append("## Counts")
    cnt = manifest.groupby("group", as_index=False).agg(count=("doc_path", "count")).sort_values("group")
    lines.append(_table(cnt))
    return "\n".join(lines)


def _render_taxonomy_rules() -> str:
    lines: list[str] = []
    lines.append("# Analysis Taxonomy Rules")
    lines.append("")
    lines.append(f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("")
    lines.append("## Group Assignment Order")
    lines.append("1. `archive`: any document under `docs/archive/`.")
    lines.append("2. `core`: canonical governance reports for the OCO bible.")
    lines.append("3. `symbol`: filename maps to specific symbol token (`EURUSD`, `GBPUSD`, `USDJPY`).")
    lines.append("4. `stage`: filename keyword maps to stage id.")
    lines.append("5. `legacy`: known historical/legacy analysis families.")
    lines.append("6. `unclassified`: everything else (should be zero in healthy state).")
    lines.append("")
    lines.append("## Stage Keyword Map")
    stage_rows = []
    for stage_id, keys in STAGE_KEYWORDS:
        stage_rows.append({"stage_id": int(stage_id), "keywords": ", ".join(keys)})
    lines.append(_table(pd.DataFrame(stage_rows)))
    lines.append("")
    lines.append("## Legacy Keyword Map")
    legacy_rows = [{"keyword": k} for k in LEGACY_KEYWORDS]
    lines.append(_table(pd.DataFrame(legacy_rows)))
    lines.append("")
    lines.append("## Core Report Set")
    core_rows = [{"doc_path": p} for p in sorted(CORE_REPORTS)]
    lines.append(_table(pd.DataFrame(core_rows)))
    return "\n".join(lines)


def run(
    *,
    docs_root: Path,
    analysis_dir: Path,
    archive_dir: Path,
    out_index_md: Path,
    out_manifest_csv: Path,
    out_gaps_md: Path,
    out_taxonomy_md: Path | None = None,
) -> tuple[pd.DataFrame, Path, Path]:
    doc_paths: list[Path] = []
    if analysis_dir.exists():
        doc_paths.extend(sorted(analysis_dir.glob("*.md")))
    if archive_dir.exists():
        doc_paths.extend(sorted(archive_dir.glob("*.md")))
    excluded_names = {"index.md", "catalog_gaps_report.md"}
    doc_paths = [p for p in doc_paths if p.name not in excluded_names]

    rows: list[dict[str, Any]] = []
    for p in doc_paths:
        c = _classify_doc(p, docs_root=docs_root)
        rows.append(
            {
                "doc_path": c.doc_path,
                "title": c.title,
                "symbol": c.symbol,
                "stage_id": c.stage_id,
                "group": c.group,
                "is_core": c.is_core,
                "is_archive": c.is_archive,
                "mtime_utc": c.mtime_utc,
            }
        )
    manifest = pd.DataFrame(rows).sort_values("doc_path").reset_index(drop=True) if rows else pd.DataFrame(
        columns=["doc_path", "title", "symbol", "stage_id", "group", "is_core", "is_archive", "mtime_utc"]
    )

    out_manifest_csv.parent.mkdir(parents=True, exist_ok=True)
    out_index_md.parent.mkdir(parents=True, exist_ok=True)
    out_gaps_md.parent.mkdir(parents=True, exist_ok=True)
    if out_taxonomy_md is not None:
        out_taxonomy_md.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(out_manifest_csv, index=False)
    out_index_md.write_text(_render_index(manifest, docs_root=docs_root), encoding="utf-8")
    out_gaps_md.write_text(_render_gaps(manifest, docs_root=docs_root), encoding="utf-8")
    if out_taxonomy_md is not None:
        out_taxonomy_md.write_text(_render_taxonomy_rules(), encoding="utf-8")
    return manifest, out_index_md, out_gaps_md


def main() -> None:
    p = argparse.ArgumentParser(description="Build docs analysis catalog and manifest")
    p.add_argument("--docs-root", default="docs")
    p.add_argument("--analysis-dir", default="docs/analysis")
    p.add_argument("--archive-dir", default="docs/archive")
    p.add_argument("--out-index-md", default="docs/analysis/index.md")
    p.add_argument("--out-manifest-csv", default="docs/analysis/catalog_manifest.csv")
    p.add_argument("--out-gaps-md", default="docs/analysis/catalog_gaps_report.md")
    p.add_argument("--out-taxonomy-md", default="docs/analysis/taxonomy_rules.md")
    args = p.parse_args()

    manifest, out_index, out_gaps = run(
        docs_root=Path(str(args.docs_root)),
        analysis_dir=Path(str(args.analysis_dir)),
        archive_dir=Path(str(args.archive_dir)),
        out_index_md=Path(str(args.out_index_md)),
        out_manifest_csv=Path(str(args.out_manifest_csv)),
        out_gaps_md=Path(str(args.out_gaps_md)),
        out_taxonomy_md=Path(str(args.out_taxonomy_md)),
    )
    print(f"wrote manifest: {args.out_manifest_csv} rows={len(manifest)}")
    print(f"wrote index: {out_index}")
    print(f"wrote gaps: {out_gaps}")
    print(f"wrote taxonomy rules: {args.out_taxonomy_md}")


if __name__ == "__main__":
    main()
