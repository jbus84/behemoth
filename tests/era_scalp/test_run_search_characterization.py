"""C2 oracle: pin run_era_eur.run_search's behavior so the engine port stays faithful.

A deterministic fake LLM writer + fixed seed make the legacy (directional) search
reproducible; the port must keep these assertions green.
"""
import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData


def _val_split(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))),
        names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float),
        mid=1.0 + np.cumsum(rng.standard_normal(n)) * 1e-4,
        cost=np.full(n, 0.2),
        test_month=np.array([f"2024-{1 + (i // 130) % 12:02d}" for i in range(n)]),
        spread_pips=np.full(n, 0.2),
    )


_FAKE = "```python\ndef signal(ctx):\n    return ctx.col('vel_z_h2')\n```"


def _run(tmp_path, monkeypatch, seed=0, budget=4):
    monkeypatch.setattr("scripts.era.llm._ollama_caller", lambda prompt: _FAKE)
    from scripts.era_scalp.run_era_eur import run_search
    splits = {"validation": _val_split()}
    return run_search(splits, "EURUSD", budget=budget, seed=seed,
                      cache_dir=str(tmp_path), select_policy="diversity")


def _sig(nodes):
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    return [(n.branch, round(float(n.score), 6)) for n in ranked]


def test_run_search_node_count(tmp_path, monkeypatch):
    nodes = _run(tmp_path, monkeypatch, budget=4)
    # 14 fade seeds + 4 expansions (fake writer always returns a valid program)
    assert len(nodes) == len(_seed_count()) + 4


def _seed_count():
    from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
    return FADE_SEED_PROGRAMS


def test_run_search_is_deterministic(tmp_path, monkeypatch):
    a = _run(tmp_path / "a", monkeypatch, seed=0, budget=4)
    b = _run(tmp_path / "b", monkeypatch, seed=0, budget=4)
    assert _sig(a) == _sig(b)


def test_run_search_golden_best(tmp_path, monkeypatch):
    """Locks the search's outcome robustly (positions 2+ are score ties, so order isn't
    asserted): node count = seeds + budget, and the UNIQUE best node's (branch, score).
    The engine port must reproduce these — score_program is parity-equivalent to
    CostAwarePerSymbolScorer, so the best score is preserved."""
    nodes = _run(tmp_path, monkeypatch, seed=0, budget=4)
    assert len(nodes) == len(_seed_count()) + 4
    valid = [n for n in nodes if n.score > -1e6 + 1]
    best = max(valid, key=lambda n: n.score)
    assert best.branch == "mean_reversion_gate"
    assert np.isclose(best.score, -5.5959, atol=1e-3), best.score
