from scripts.fx_coint.gate import Verdict, classify


def test_set_when_floor_clears_cost():
    v = classify(structure=True, reversion=True, fdr_pass=True,
                 floor=2e-4, ceiling=5e-4, cost=1e-4, floor_multiple=1.0)
    assert v == Verdict.SET


def test_execution_gated_when_cost_between_floor_and_ceiling():
    v = classify(structure=True, reversion=True, fdr_pass=True,
                 floor=0.5e-4, ceiling=5e-4, cost=1e-4, floor_multiple=1.0)
    assert v == Verdict.EXECUTION_GATED


def test_nogo_when_ceiling_below_cost():
    v = classify(structure=True, reversion=True, fdr_pass=True,
                 floor=0.2e-4, ceiling=0.8e-4, cost=1e-4, floor_multiple=1.0)
    assert v == Verdict.NOGO


def test_nogo_when_structure_or_reversion_absent():
    assert classify(structure=False, reversion=True, fdr_pass=True,
                    floor=9e-4, ceiling=9e-4, cost=1e-4, floor_multiple=1.0) == Verdict.NOGO
    assert classify(structure=True, reversion=False, fdr_pass=True,
                    floor=9e-4, ceiling=9e-4, cost=1e-4, floor_multiple=1.0) == Verdict.NOGO
    assert classify(structure=True, reversion=True, fdr_pass=False,
                    floor=9e-4, ceiling=9e-4, cost=1e-4, floor_multiple=1.0) == Verdict.NOGO
