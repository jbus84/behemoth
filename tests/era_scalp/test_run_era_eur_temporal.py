import numpy as np

from scripts.era.puct import Node
from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp.run_era_eur import (
    _concat_trade_splits,
    _temporal_tiebreak,
    temporal_annotation,
)


def _split(n, month_labels, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(WHITELIST)))
    return TradeSplitData(
        X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float),
        mid=1.0 + np.cumsum(rng.standard_normal(n)) * 1e-4,
        cost=np.full(n, 0.2),
        test_month=np.array(month_labels),
        spread_pips=np.full(n, 0.2),
    )


def test_concat_trade_splits_lengths_and_fields():
    a = _split(100, ["2023-01"] * 100, seed=1)
    b = _split(60, ["2024-01"] * 60, seed=2)
    c = _concat_trade_splits(a, b)
    assert c.X.shape[0] == 160
    assert c.mid.shape[0] == 160 and c.cost.shape[0] == 160
    assert c.test_month.shape[0] == 160
    assert c.spread_pips.shape[0] == 160
    assert list(c.test_month[:2]) == ["2023-01", "2023-01"]
    assert list(c.test_month[-2:]) == ["2024-01", "2024-01"]


def test_temporal_tiebreak_prefers_robust_on_score_tie():
    n1 = Node(payload="a", score=1.230, parent=None)
    n2 = Node(payload="b", score=1.234, parent=None)
    vbi = {
        id(n1): {"status": "ok", "worst_window_p_positive": 0.9},
        id(n2): {"status": "ok", "worst_window_p_positive": 0.3},
    }
    out = _temporal_tiebreak([n2, n1], vbi)
    assert out[0] is n1   # higher worst-window-p wins the score tie


def test_temporal_tiebreak_missing_verdict_sorts_last():
    n1 = Node(payload="a", score=1.230, parent=None)
    n2 = Node(payload="b", score=1.234, parent=None)
    vbi = {id(n1): {"status": "ok", "worst_window_p_positive": 0.8}}  # n2 missing
    out = _temporal_tiebreak([n2, n1], vbi)
    assert out[0] is n1


def test_temporal_annotation_smoke():
    # A signal that trades across several months; tiny MCMC for speed.
    months = []
    for mlabel in ["2023-11", "2023-12", "2024-01", "2024-02"]:
        months += [mlabel] * 600
    sp = {"train": _split(1200, months[:1200], seed=3),
          "validation": _split(1200, months[1200:], seed=4)}
    src = "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n"
    v = temporal_annotation(src, sp, "EURUSD", min_trades=30,
                            num_warmup=100, num_samples=100, num_chains=1)
    assert v is None or ("status" in v)
    if v is not None and v["status"] == "ok":
        assert "worst_window_p_positive" in v and "p_positive" in v
