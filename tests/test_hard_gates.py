import json
from pathlib import Path

import pandas as pd

import behemoth.config as cfg


def _require(path: str) -> Path:
    p = Path(path)
    assert p.exists(), f"Missing required analysis artifact: {path}"
    return p


def test_repro_manifest_matches_config():
    p = _require("data/analysis/repro_manifest.json")
    manifest = json.loads(p.read_text())
    config = manifest.get("config", {})
    assert float(config.get("Z_ENTRY_MOM")) == cfg.Z_ENTRY_MOM
    assert float(config.get("Z_STOP")) == cfg.Z_STOP
    assert int(config.get("MIN_GAP_BARS")) == cfg.MIN_GAP_BARS
    assert int(config.get("LOOKBACK_BARS")) == cfg.LOOKBACK_BARS
    assert float(config.get("ACTIVE_LEG_LOW")) == cfg.ACTIVE_LEG_LOW
    assert float(config.get("ACTIVE_LEG_HIGH")) == cfg.ACTIVE_LEG_HIGH


def test_alignment_shift_penalty():
    for path in [
        "data/analysis/m5_alignment_sensitivity.csv",
        "data/analysis/m15_alignment_sensitivity.csv",
    ]:
        df = pd.read_csv(_require(path))
        means = df.groupby("shift")["mean_pnl"].mean()
        assert 0 in means.index
        assert 1 in means.index
        # One-bar misalignment should not improve mean PnL.
        assert means.loc[1] <= means.loc[0]


def test_fill_price_slippage_penalty():
    for path in [
        "data/analysis/m5_fill_price_sensitivity.csv",
        "data/analysis/m15_fill_price_sensitivity.csv",
    ]:
        df = pd.read_csv(_require(path))
        for mode in ["close", "next_close", "mean"]:
            base = df[(df["variant"] == f"{mode}_slip_0.0") & (df["guardrail"])]
            slip = df[(df["variant"] == f"{mode}_slip_0.1") & (df["guardrail"])]
            assert not base.empty and not slip.empty
            assert float(slip["mean_pnl"].iloc[0]) <= float(base["mean_pnl"].iloc[0])


def test_guardrail_skips_negative_expectancy():
    for path in [
        "data/analysis/m5_guardrail_skip_stats.csv",
        "data/analysis/m15_guardrail_skip_stats.csv",
    ]:
        df = pd.read_csv(_require(path))
        assert float(df["skipped_mean_pnl"].iloc[0]) < 0.0
