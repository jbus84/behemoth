from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_docs_catalog import run


def test_build_docs_catalog_outputs_manifest_and_index(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    analysis = docs_root / "analysis"
    archive = docs_root / "archive"
    archive_analysis = archive / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    archive_analysis.mkdir(parents=True, exist_ok=True)

    (analysis / "data_reliability_report.md").write_text("# dr\n", encoding="utf-8")
    (analysis / "eurusd_tick_opportunity_mining_report.md").write_text("# eur\n", encoding="utf-8")
    (analysis / "EURUSD_candidate_2025-07_h6_london_k2_drift.md").write_text(
        "# eur candidate\n", encoding="utf-8"
    )
    (analysis / "eurusd_offset_tickbar_robustness_report.md").write_text(
        "# eur offset\n", encoding="utf-8"
    )
    (analysis / "EURUSD_stage12_api_parity_report.md").write_text(
        "# eur parity\n", encoding="utf-8"
    )
    (analysis / "EURUSD_dukascopy_testclient_execution_parity_report.md").write_text(
        "# eur execution parity\n", encoding="utf-8"
    )
    (analysis / "oco_execution_monte_carlo_report.md").write_text("# mc\n", encoding="utf-8")
    (analysis / "index.md").write_text("# stale\n", encoding="utf-8")
    (archive_analysis / "eurusd_tick_opportunity_ml_ready_report.md").write_text(
        "# old\n", encoding="utf-8"
    )

    manifest, out_index, out_gaps = run(
        docs_root=docs_root,
        analysis_dir=analysis,
        archive_dir=archive,
        out_index_md=analysis / "index.md",
        out_manifest_csv=analysis / "catalog_manifest.csv",
        out_gaps_md=analysis / "catalog_gaps_report.md",
        out_taxonomy_md=analysis / "taxonomy_rules.md",
    )

    assert not manifest.empty
    assert out_index.exists()
    assert out_gaps.exists()
    assert (analysis / "catalog_manifest.csv").exists()

    m = pd.read_csv(analysis / "catalog_manifest.csv")
    assert "analysis/data_reliability_report.md" in set(m["doc_path"].astype(str))
    assert "analysis/eurusd_tick_opportunity_mining_report.md" in set(m["doc_path"].astype(str))
    candidate_row = m[m["doc_path"].astype(str) == "analysis/EURUSD_candidate_2025-07_h6_london_k2_drift.md"]
    assert not candidate_row.empty
    assert candidate_row.iloc[0]["group"] == "candidate"
    offset_row = m[m["doc_path"].astype(str) == "analysis/eurusd_offset_tickbar_robustness_report.md"]
    assert not offset_row.empty
    assert int(offset_row.iloc[0]["stage_id"]) == 8
    assert offset_row.iloc[0]["group"] == "candidate"
    stage12_row = m[m["doc_path"].astype(str) == "analysis/EURUSD_stage12_api_parity_report.md"]
    assert not stage12_row.empty
    assert stage12_row.iloc[0]["group"] == "compatibility"
    execution_parity_row = m[
        m["doc_path"].astype(str) == "analysis/EURUSD_dukascopy_testclient_execution_parity_report.md"
    ]
    assert not execution_parity_row.empty
    assert execution_parity_row.iloc[0]["group"] == "compatibility"
    assert "archive/analysis/eurusd_tick_opportunity_ml_ready_report.md" in set(
        m["doc_path"].astype(str)
    )

    index_text = out_index.read_text(encoding="utf-8")
    assert "## Active / Core Reports" in index_text
    assert "## Active Symbol Reports" in index_text
    assert "## Candidate / Experimental Reports" in index_text
    assert "## Compatibility / Legacy Reports" in index_text
    assert "## Archive Reports" in index_text

    active_symbol_block = index_text.split("## Active Symbol Reports", maxsplit=1)[1].split(
        "## Candidate / Experimental Reports", maxsplit=1
    )[0]
    assert "[Eurusd Tick Opportunity Mining Report](eurusd_tick_opportunity_mining_report.md)" in (
        active_symbol_block
    )
    assert "Eurusd Candidate 2025 07 H6 London K2 Drift" not in active_symbol_block
    assert "Eurusd Offset Tickbar Robustness Report" not in active_symbol_block
    assert "Eurusd Stage12 Api Parity Report" not in active_symbol_block

    candidate_block = index_text.split("## Candidate / Experimental Reports", maxsplit=1)[1].split(
        "## Compatibility / Legacy Reports", maxsplit=1
    )[0]
    assert "[Eurusd Candidate 2025 07 H6 London K2 Drift](EURUSD_candidate_2025-07_h6_london_k2_drift.md)" in (
        candidate_block
    )
    assert "[Eurusd Offset Tickbar Robustness Report](eurusd_offset_tickbar_robustness_report.md)" in (
        candidate_block
    )

    compatibility_block = index_text.split(
        "## Compatibility / Legacy Reports", maxsplit=1
    )[1].split("## Archive Reports", maxsplit=1)[0]
    assert "[Eurusd Stage12 Api Parity Report](EURUSD_stage12_api_parity_report.md)" in (
        compatibility_block
    )
    assert "[Eurusd Dukascopy Testclient Execution Parity Report](EURUSD_dukascopy_testclient_execution_parity_report.md)" in (
        compatibility_block
    )

    archive_block = index_text.split("## Archive Reports", maxsplit=1)[1]
    assert "[Eurusd Tick Opportunity Ml Ready Report](../archive/analysis/eurusd_tick_opportunity_ml_ready_report.md)" in (
        archive_block
    )

    gaps_text = out_gaps.read_text(encoding="utf-8")
    assert "| candidate" in gaps_text
    assert "| archive" in gaps_text

    taxonomy_text = (analysis / "taxonomy_rules.md").read_text(encoding="utf-8")
    assert "1. `archive`" in taxonomy_text
    assert "3. `candidate`" in taxonomy_text
    assert "4. `compatibility`" in taxonomy_text
    assert "## Candidate Keyword Map" in taxonomy_text
