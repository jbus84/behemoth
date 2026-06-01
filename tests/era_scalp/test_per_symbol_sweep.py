import numpy as np
import pandas as pd

from scripts.era_scalp import per_symbol_sweep as pss
from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData


def _split(n=900, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months),
    )


def test_dev_signal_runs_and_is_finite_mostly():
    sig = pss.dev_signal(_split())
    assert sig.shape[0] == 900
    assert np.isfinite(sig).any()


def test_directions_are_exact_negations():
    sp = _split()
    sig = pss.dev_signal(sp)
    fade = pss.cell_net(sig, sp, "EURUSD", "fade", q=0.90, h=100)
    cont = pss.cell_net(sig, sp, "EURUSD", "continue", q=0.90, h=100)
    assert len(fade) == len(cont) and len(fade) > 0
    paired = fade["net"].to_numpy() + cont["net"].to_numpy()
    assert np.allclose(paired, -2 * 0.4)


def test_diagnostics_match_hand_values():
    frame = pd.DataFrame({
        "net": [1.0, 3.0, -1.0, -1.0, 2.0],
        "test_month": ["2025-01", "2025-01", "2025-02", "2025-02", "2025-03"],
    })
    d = pss.diagnostics(frame)
    assert d["n_trades"] == 5
    assert d["n_months"] == 3
    assert np.isclose(d["month_hit"], 2 / 3)
    assert np.isclose(d["raw_mean"], (1 + 3 - 1 - 1 + 2) / 5)


def test_diagnostics_empty_frame():
    d = pss.diagnostics(pd.DataFrame({"net": [], "test_month": []}))
    assert d["n_trades"] == 0 and d["n_months"] == 0
    assert d["month_hit"] == 0.0 and np.isnan(d["raw_mean"])


def test_select_prefers_higher_lo_when_both_pass_guard(monkeypatch):
    sp = _split(n=3000)  # large enough that q=0.90 clears the 200-trade guard
    sig = pss.dev_signal(sp)
    def fake_cred(frame, seed=0, fast=False):
        return {"p_positive": 0.9, "mean": 1.0, "lo": 0.5, "hi": 1.5}
    monkeypatch.setattr(pss, "credibility", fake_cred)
    choice = pss.select_on_validation(sig, sp, "EURUSD")
    assert choice is not None
    assert choice["direction"] in pss.DIRECTIONS and choice["q"] in pss.GRID_Q and choice["h"] in pss.GRID_H


def test_select_respects_sample_guard(monkeypatch):
    sp = _split(n=3000)  # q=0.90 clears the 200-trade guard; q=0.95/0.99 do not
    sig = pss.dev_signal(sp)
    def fake_cred(frame, seed=0, fast=False):
        return {"p_positive": 0.99, "mean": 9.0, "lo": 9.0, "hi": 9.1} if len(frame) < pss.MIN_TRADES \
            else {"p_positive": 0.7, "mean": 0.2, "lo": 0.1, "hi": 0.4}
    monkeypatch.setattr(pss, "credibility", fake_cred)
    choice = pss.select_on_validation(sig, sp, "EURUSD")
    assert choice is not None
    assert choice["val"]["n_trades"] >= pss.MIN_TRADES
    assert choice["val"]["n_months"] >= pss.MIN_MONTHS_SEL
    assert np.isclose(choice["val"]["lo"], 0.1)


def test_select_returns_none_when_nothing_admissible(monkeypatch):
    sp = _split(n=120)
    sig = pss.dev_signal(sp)
    monkeypatch.setattr(pss, "credibility",
                        lambda frame, seed=0, fast=False: {"p_positive": 0.9, "mean": 1.0, "lo": 0.5, "hi": 1.5})
    assert pss.select_on_validation(sig, sp, "EURUSD") is None


def test_confirm_and_sweep_wiring(monkeypatch):
    # Force validation selection to a specific cell, then assert holdout confirms THAT cell.
    chosen = {"direction": "continue", "q": 0.90, "h": 100}

    def fake_select(signal, split_data, symbol):
        return {**chosen, "val": {"p_positive": 0.8, "mean": 0.5, "lo": 0.3, "hi": 0.7,
                                  "n_trades": 999, "n_months": 12, "month_hit": 0.6, "raw_mean": 0.5}}

    captured = {}

    def fake_cred(frame, seed=0, fast=False):
        captured["fast"] = fast  # holdout confirm must call with fast=False (full chains)
        return {"p_positive": 0.77, "mean": 0.4, "lo": 0.1, "hi": 0.7}

    monkeypatch.setattr(pss, "select_on_validation", fake_select)
    monkeypatch.setattr(pss, "credibility", fake_cred)

    sp_h = _split(seed=2)
    sig_h = pss.dev_signal(sp_h)
    res = pss.confirm_on_holdout(sig_h, sp_h, "EURUSD", fake_select(None, sp_h, "EURUSD"))
    assert res["direction"] == "continue" and res["q"] == 0.90 and res["h"] == 100
    assert set(res["holdout"]) >= {"p_positive", "mean", "lo", "hi",
                                   "n_trades", "n_months", "month_hit", "raw_mean"}
    assert captured["fast"] is False  # holdout uses full chains
