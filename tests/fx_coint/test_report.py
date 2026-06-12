import json

from scripts.fx_coint.report import write_report


def test_write_report_emits_json_and_md(tmp_path):
    rows = [{
        "timeframe": "1D", "universe": "pairwise", "base": "GBPUSD", "hedge": "EURUSD",
        "fraction_stationary": 0.8, "fdr_pass": True, "half_life": 12.0,
        "reversion_frac": 0.61, "n_events": 240,
        "floor": 2e-4, "ceiling": 6e-4,
        "cost_by_markup": {"0.0": 1e-4, "0.3": 1.2e-4, "0.6": 1.4e-4, "1.0": 1.8e-4},
        "verdict_by_markup": {"0.0": "SET", "0.3": "SET", "0.6": "EXECUTION_GATED", "1.0": "NOGO"},
    }]
    out_json = tmp_path / "screen.json"
    out_md = tmp_path / "screen.md"
    write_report(rows, out_json, out_md)
    loaded = json.loads(out_json.read_text())
    assert loaded["rows"][0]["base"] == "GBPUSD"
    assert loaded["summary"]["n_set_at_zero_markup"] == 1
    md = out_md.read_text()
    assert "GBPUSD" in md and "Verdict" in md
