from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_docs_catalog import run


def test_build_docs_catalog_outputs_manifest_and_index(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    analysis = docs_root / "analysis"
    archive = docs_root / "archive"
    analysis.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)

    (analysis / "data_reliability_report.md").write_text("# dr\n", encoding="utf-8")
    (analysis / "eurusd_tick_opportunity_mining_report.md").write_text("# eur\n", encoding="utf-8")
    (analysis / "oco_execution_monte_carlo_report.md").write_text("# mc\n", encoding="utf-8")
    (analysis / "index.md").write_text("# stale\n", encoding="utf-8")
    (archive / "legacy_strategy_guide.md").write_text("# old\n", encoding="utf-8")

    manifest, out_index, out_gaps = run(
        docs_root=docs_root,
        analysis_dir=analysis,
        archive_dir=archive,
        out_index_md=analysis / "index.md",
        out_manifest_csv=analysis / "catalog_manifest.csv",
        out_gaps_md=analysis / "catalog_gaps_report.md",
    )

    assert not manifest.empty
    assert out_index.exists()
    assert out_gaps.exists()
    assert (analysis / "catalog_manifest.csv").exists()

    m = pd.read_csv(analysis / "catalog_manifest.csv")
    assert "analysis/data_reliability_report.md" in set(m["doc_path"].astype(str))
    assert "analysis/eurusd_tick_opportunity_mining_report.md" in set(m["doc_path"].astype(str))
    assert "archive/legacy_strategy_guide.md" in set(m["doc_path"].astype(str))
