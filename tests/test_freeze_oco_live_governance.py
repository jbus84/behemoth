"""Tests for freeze_oco_live_governance module."""

import json

import pandas as pd


def test_manifest_deploy_verdict_no_go_for_empty_universe(tmp_path, monkeypatch):
    """An empty reduced-states CSV yields a manifest whose deploy_verdict is
    the canonical NO_GO, with an empty state_universe."""
    from scripts.freeze_oco_live_governance import _state_universe

    empty_states = tmp_path / "EURUSD_oco_reduced_states.csv"
    pd.DataFrame(
        columns=[
            "symbol",
            "bar_ticks",
            "horizon",
            "state_id",
            "family",
            "barrier_pips",
            "regime_desc",
        ]
    ).to_csv(empty_states, index=False)

    states, _sha = _state_universe(empty_states)
    assert states.empty
    # deploy_verdict is derived purely from the universe count:
    from scripts.freeze_oco_live_governance import _deploy_verdict

    assert _deploy_verdict(0) == "NO_GO"
    assert _deploy_verdict(5) == "GO"


def test_live_freeze_emits_schema_v3_with_family_and_bundle_relative_paths(tmp_path, monkeypatch):
    """Freeze must produce a v3 lock whose artifact paths are bundle-relative."""
    from scripts import freeze_oco_live_governance as freeze

    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-05"
    bundle_dir.mkdir(parents=True)

    # Stage minimal fixture artifacts
    wfo_cfg = bundle_dir / "eurusd_wfo.yaml"
    wfo_cfg.write_text("threshold_mode: rolling\n")
    red_cfg = bundle_dir / "eurusd_reduced.yaml"
    red_cfg.write_text("locked_quantile: 0.9\nselection_mode: auto\n")
    states_csv = bundle_dir / "eurusd_oco_allowed_states.csv"
    pd.DataFrame(
        {
            "symbol": ["EURUSD"],
            "bar_ticks": [1],
            "horizon": [1],
            "state_id": ["s1"],
            "family": ["f1"],
            "barrier_pips": [1.0],
            "regime_desc": ["r1"],
        }
    ).to_csv(states_csv, index=False)
    pred_parquet = bundle_dir / "eurusd_oco_locked_predictions.parquet"
    pred_parquet.write_bytes(b"pred")
    tick_summary = bundle_dir / "eurusd_oco_tick_exact_summary.csv"
    pd.DataFrame({"overall_pass": [True]}).to_csv(tick_summary, index=False)
    red_summary = bundle_dir / "eurusd_oco_reduced_summary.csv"
    pd.DataFrame({"capacity_pass_monthly_or_annual": [True]}).to_csv(red_summary, index=False)
    caps_csv = bundle_dir / "eurusd_stop_limit_tickfill_caps.csv"
    pd.DataFrame({"cap_pips": [1.0], "mean_per_signal_full_overshoot": [0.5]}).to_csv(
        caps_csv, index=False
    )
    model_cbm = bundle_dir / "EURUSD_model_2026-05.cbm"
    model_cbm.write_bytes(b"cbm")
    model_thr = bundle_dir / "EURUSD_model_2026-05.json"
    model_thr.write_text(json.dumps({"threshold_mode": "rolling"}))

    monkeypatch.setattr(
        freeze, "_latest_model_pair", lambda symbol, models_dir=None: (model_cbm, model_thr)
    )

    paths = {
        "wfo_config": wfo_cfg,
        "reduced_config": red_cfg,
        "reduced_states": states_csv,
        "predictions": pred_parquet,
        "tick_exact_summary": tick_summary,
        "reduced_summary": red_summary,
        "tick_fill_caps": caps_csv,
    }

    manifest = freeze._build_manifest(
        symbol="EURUSD",
        paths=paths,
        out_dir=bundle_dir,
        cadence_days=30,
        anchor_day_utc=1,
        window_days=3,
        git_snapshot={"branch": "main", "commit": "deadbeef", "dirty": False},
    )

    assert manifest["schema_version"] == 3
    assert manifest["bundle"]["family"] == "oco_first_touch"
    assert "artifacts" in manifest
    for key, entry in manifest["artifacts"].items():
        if isinstance(entry, dict) and "path" in entry:
            assert not entry["path"].startswith("/"), key
            assert ".." not in entry["path"].split("/"), key
