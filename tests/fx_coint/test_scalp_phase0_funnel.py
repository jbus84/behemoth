from scripts.fx_coint.phase0_scalp_funnel import apply_stopping_rules, rank_families


def test_rank_families():
    results = {
        "A": {"results": {"h1": {"net_lb95_bps": 0.5, "verdict": "PASS", "n_entries": 50}}},
        "B": {"results": {"h1": {"net_lb95_bps": -0.2, "verdict": "NEAR_MISS", "n_entries": 30}}},
        "C": {"results": {"h1": {"net_lb95_bps": -1.0, "verdict": "FAIL", "n_entries": 10}}},
        "D": {"results": {"h1": {"net_lb95_bps": -0.8, "verdict": "FAIL", "n_entries": 5}}},
    }
    ranked = rank_families(results)
    assert ranked[0][0] == "A"
    assert ranked[0][1]["best_verdict"] == "PASS"


def test_stopping_rules_kill():
    results = {f: {"results": {"h1": {"verdict": "FAIL"}}} for f in "ABCD"}
    assert apply_stopping_rules(results) == "STOP"


def test_stopping_rules_continue():
    results = {"A": {"results": {"h1": {"verdict": "PASS"}}},
               "B": {"results": {"h1": {"verdict": "FAIL"}}}}
    assert apply_stopping_rules(results) == "CONTINUE"
