"""Tests for the per-symbol mining deep-audit report builder."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_mining_deep_report import (
    DEFAULT_SYMBOLS,
    FAMILY_CSVS,
    _per_family_summary,
    _per_regime_table,
    _selection_funnel,
    _top_n,
    build_report_for_symbol,
    main,
)


def _write_minimal_candidate_csv(
    path: Path, *, family: str, n: int, base_z: float = 0.0,
) -> None:
    """Write a tiny candidate CSV with the columns the report reads."""
    rng = np.random.default_rng(hash(family) & 0xFFFFFFFF)
    df = pd.DataFrame({
        "candidate_id": [f"{family[:3]}{i:03d}" for i in range(n)],
        "family": family,
        "bar_ticks": rng.choice([100, 1000, 2000], size=n),
        "horizon": rng.choice([1, 3, 5], size=n),
        "regime_desc": rng.choice(
            ["london", "ny_overlap;k=1", "asia;down=3;rr=2"], size=n,
        ),
        "random_baseline_z": rng.normal(base_z, 1.0, size=n),
        "mean_gross_pips_train": rng.normal(0.0, 0.5, size=n),
        "test_count": rng.integers(500, 5000, size=n),
        "selection_pass": rng.random(n) < 0.2,
        "near_miss": rng.random(n) < 0.1,
    })
    df.to_csv(path, index=False)


def _stage_analysis_dir(
    tmp_path: Path,
    symbol: str = "EURUSD",
    families: tuple[str, ...] = ("directional", "oco_first_touch"),
) -> Path:
    analysis_dir = tmp_path / "tick_opportunity_mining"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    # Per-family CSVs (only the named families get content; the rest are
    # absent/empty — the report must handle both).
    for fam in families:
        suffix = FAMILY_CSVS[fam]
        _write_minimal_candidate_csv(
            analysis_dir / f"{symbol}{suffix}", family=fam, n=12,
            base_z=2.0 if fam == "directional" else -1.5,
        )
    # candidate_summary stub.
    pd.DataFrame([
        {"library": "directional", "rows_total": 12, "rows_pass": 3,
         "pass_rate": 0.25, "mean_gross_all": 0.05, "mean_baseline_z": 2.0},
        {"library": "oco", "rows_total": 12, "rows_pass": 0,
         "pass_rate": 0.0, "mean_gross_all": -0.5, "mean_baseline_z": -1.5},
    ]).to_csv(analysis_dir / f"{symbol}_candidate_summary.csv", index=False)
    # Fills parquet — small fixture.
    fills = pd.DataFrame({
        "family": ["directional"] * 4 + ["oco_first_touch"] * 4,
        "split": ["train", "test", "train", "test"] * 2,
        "gross_pips": [1.2, -0.5, 0.8, 0.1, -0.3, -1.1, 0.4, -0.2],
    })
    (analysis_dir / "candidate_fills").mkdir(exist_ok=True)
    fills.to_parquet(
        analysis_dir / "candidate_fills" / f"{symbol}_candidate_fills.parquet",
        index=False,
    )
    return analysis_dir


def test_per_family_summary_handles_mixed_empty_and_populated():
    fams = {
        "directional": pd.DataFrame({
            "random_baseline_z": [1.0, 2.0, 3.0],
            "mean_gross_pips_train": [0.1, 0.2, -0.1],
            "selection_pass": [True, False, True],
        }),
        "no_touch": pd.DataFrame(),
    }
    out = _per_family_summary(fams)
    assert set(out["family"]) == {"directional", "no_touch"}
    dr = out[out["family"] == "directional"].iloc[0]
    nt = out[out["family"] == "no_touch"].iloc[0]
    assert dr["n_candidates"] == 3
    assert dr["selection_pass"] == 2
    assert abs(dr["mean_baseline_z"] - 2.0) < 1e-9
    assert nt["n_candidates"] == 0
    assert np.isnan(nt["mean_baseline_z"])


def test_per_regime_table_coarsens_extra_segments():
    """regime_desc with `;k=1` or `;down=3;rr=2` suffixes should collapse
    onto the base regime so per-param fan-out doesn't fragment the rollup."""
    df = pd.DataFrame({
        "random_baseline_z": [1.0, 2.0, -0.5, 0.5],
        "regime_desc": ["london;k=1", "london;k=2", "asia", "asia;down=3;rr=2"],
        "selection_pass": [True, True, False, False],
    })
    out = _per_regime_table(df)
    assert set(out["regime"]) == {"london", "asia"}
    london = out[out["regime"] == "london"].iloc[0]
    assert london["n"] == 2
    assert abs(london["mean_z"] - 1.5) < 1e-9


def test_top_n_orders_by_baseline_z():
    df = pd.DataFrame({
        "candidate_id": ["a", "b", "c"],
        "family": ["x"] * 3,
        "random_baseline_z": [0.5, 3.0, -2.0],
    })
    top = _top_n(df, n=2, ascending=False)
    assert list(top["candidate_id"]) == ["b", "a"]
    bot = _top_n(df, n=2, ascending=True)
    assert list(bot["candidate_id"]) == ["c", "a"]


def test_selection_funnel_buckets_candidates_correctly():
    df = pd.DataFrame({
        "selection_pass": [True, False, False, False],
        "near_miss": [False, True, False, False],
    })
    out = _selection_funnel({"x": df})
    row = out.iloc[0]
    assert row["candidates"] == 4
    assert row["selection_pass"] == 1
    assert row["near_miss"] == 1
    assert row["neither"] == 2


def test_build_report_for_symbol_writes_markdown(tmp_path: Path):
    analysis_dir = _stage_analysis_dir(tmp_path)
    out_dir = tmp_path / "out"
    path = build_report_for_symbol(
        analysis_dir=analysis_dir, symbol="EURUSD", out_dir=out_dir,
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # Must include the per-family summary and the two leaderboards.
    assert "# EURUSD mining deep report" in text
    assert "## Per-family summary (deep)" in text
    assert "## Top 20 positive-edge candidates" in text
    assert "## Top 20 negative-edge candidates" in text
    assert "## Fill density" in text
    # Empty families show up as a row with zeros, not as a missing line.
    assert "no_touch" in text


def test_build_report_handles_missing_files_gracefully(tmp_path: Path):
    """If no per-family CSV exists for a symbol, the report still writes
    (every family shows as 0 candidates)."""
    analysis_dir = tmp_path / "empty"
    analysis_dir.mkdir()
    # Stub only the summary so main() picks the symbol up.
    pd.DataFrame(columns=["library"]).to_csv(
        analysis_dir / "EURUSD_candidate_summary.csv", index=False,
    )
    out_dir = tmp_path / "out"
    path = build_report_for_symbol(
        analysis_dir=analysis_dir, symbol="EURUSD", out_dir=out_dir,
    )
    text = path.read_text(encoding="utf-8")
    assert "# EURUSD mining deep report" in text


def test_main_builds_index_when_multiple_symbols(tmp_path: Path, monkeypatch):
    """main() writes a cross-symbol index.md when 2+ reports are produced."""
    analysis_dir = tmp_path / "ad"
    analysis_dir.mkdir()
    for sym in ("EURUSD", "GBPUSD"):
        _stage_analysis_dir(tmp_path, symbol=sym)
        # _stage_analysis_dir nests under tmp_path/tick_opportunity_mining;
        # move what we need into our chosen analysis_dir for this test.
    # Use the analysis dir _stage_analysis_dir created — same for both syms.
    real_ad = tmp_path / "tick_opportunity_mining"
    out_dir = tmp_path / "out2"
    argv = ["build_mining_deep_report.py",
            "--analysis-dir", str(real_ad),
            "--out-dir", str(out_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    code = main()
    assert code == 0
    assert (out_dir / "EURUSD_mining_deep_report.md").exists()
    assert (out_dir / "GBPUSD_mining_deep_report.md").exists()
    assert (out_dir / "index.md").exists()


def test_default_symbols_matches_six_majors():
    assert set(DEFAULT_SYMBOLS) == {
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
    }


def test_main_exits_nonzero_when_no_summary_files(tmp_path: Path, monkeypatch):
    out_dir = tmp_path / "out"
    argv = ["build_mining_deep_report.py",
            "--analysis-dir", str(tmp_path / "empty"),
            "--out-dir", str(out_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    code = main()
    assert code == 1
