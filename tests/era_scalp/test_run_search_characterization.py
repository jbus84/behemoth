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


# ── Rich-branch coverage ─────────────────────────────────────────────────────
# The default-path tests above leave the atomic / self-correct / dimension-locked /
# llm-prior branches (~60% of run_search) unexercised. These pin them with deterministic
# writer stubs so the engine port (run_search_rich) reproduces each branch faithfully.

_GOOD = "```python\ndef signal(ctx):\n    return ctx.col('vel_z_h2')\n```"
_BAD = "```python\ndef signal(ctx):\n    return undefined_name_xyz\n```"
_COMP = {"skeleton": "simple", "operators": {"base": "slow_ewma"}, "params": {"alpha": 0.02}}


def _run_rich(tmp_path, monkeypatch, stubs, **kw):
    """Run run_search with the era.llm writers (imported into run_era_eur) replaced by
    deterministic stubs. `stubs` maps writer attr name -> replacement callable."""
    import scripts.era_scalp.run_era_eur as R
    monkeypatch.setattr("scripts.era.llm._ollama_caller", lambda prompt: _GOOD)  # safety net
    for attr, fn in stubs.items():
        monkeypatch.setattr(R, attr, fn)
    splits = {"validation": _val_split()}
    return R.run_search(splits, "EURUSD", budget=4, seed=0,
                        cache_dir=str(tmp_path), select_policy="diversity", **kw)


def _best(nodes):
    valid = [n for n in nodes if n.score > -1e6 + 1]
    return valid, max(valid, key=lambda n: n.score)


def test_run_search_atomic_mode(tmp_path, monkeypatch):
    """Atomic mode (fair-price): compositions instead of source; propose/recombine return
    composition dicts. Distinct seed set + distinct best from the legacy path."""
    from scripts.era_scalp.fair_seeds import FAIR_SEED_COMPOSITIONS
    nodes = _run_rich(
        tmp_path, monkeypatch,
        {"propose_atomic_change": lambda *a, **k: (dict(_COMP), 0.5),
         "recombine_atomic_compositions": lambda *a, **k: (dict(_COMP), 0.5)},
        atomic_mode=True, fair_price_mode=True,
    )
    assert len(nodes) == len(FAIR_SEED_COMPOSITIONS) + 4
    valid, best = _best(nodes)
    assert best.branch == "hasbrouck_efficient"
    assert np.isclose(best.score, 3.413275, atol=1e-3), best.score


def test_run_search_self_correct(tmp_path, monkeypatch):
    """Self-correction: every proposal fails to compile, the repair writer returns a
    valid program → the corrected expansions are admitted (not stuck at the -1e6 floor)."""
    nodes = _run_rich(
        tmp_path, monkeypatch,
        {"propose_branch_program": lambda *a, **k: _BAD,
         "self_correct_program": lambda *a, **k: _GOOD},
        self_correct=True,
    )
    assert len(nodes) == len(_seed_count()) + 4
    valid, best = _best(nodes)
    assert len(valid) == 21
    assert best.branch == "mean_reversion_gate"
    assert np.isclose(best.score, -5.5959, atol=1e-3), best.score


def test_run_search_dimension_locked(tmp_path, monkeypatch):
    """Dimension-locked proposals (legacy path): one tweak per CONCEPT_TAXONOMY dimension."""
    nodes = _run_rich(
        tmp_path, monkeypatch,
        {"propose_dimension_locked_program": lambda *a, **k: (_GOOD, 0.5)},
        dimension_locked=True,
    )
    assert len(nodes) == len(_seed_count()) + 4
    _valid, best = _best(nodes)
    assert best.branch == "mean_reversion_gate"
    assert np.isclose(best.score, -5.5959, atol=1e-3), best.score


def test_run_search_llm_prior(tmp_path, monkeypatch):
    """LLM-prior proposals: writer returns (src, confidence); prior feeds the PUCT bonus."""
    nodes = _run_rich(
        tmp_path, monkeypatch,
        {"propose_branch_program_with_prior": lambda *a, **k: (_GOOD, 0.8)},
        use_llm_prior=True,
    )
    assert len(nodes) == len(_seed_count()) + 4
    _valid, best = _best(nodes)
    assert best.branch == "mean_reversion_gate"
    assert np.isclose(best.score, -5.5959, atol=1e-3), best.score
