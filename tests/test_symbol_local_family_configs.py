from pathlib import Path

import yaml

ACTIVE_SYMBOLS = ("eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad")
FAMILIES = (
    "oco_asymmetric",
    "directional_inverse",
    "directional_run",
    "double_touch",
    "pullback",
    "no_touch",
)


# Candidate library each family's reduced-core selection must read from. Mining
# writes candidate CSVs per *library*, not per family; the directional library
# file holds directional/inverse/run/double_touch/pullback. A reduced-core
# config pointing at a family-named candidate CSV (e.g. *_pullback_candidates.csv)
# references a file that mining never produces -> FileNotFound at selection time.
CANDIDATE_LIBRARY = {
    "oco_asymmetric": "oco_asymmetric",
    "directional_inverse": "directional",
    "directional_run": "directional",
    "double_touch": "directional",
    "pullback": "directional",
    "no_touch": "no_touch",
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_symbol_local_wfo_configs_exist_and_are_family_driven() -> None:
    for symbol in ACTIVE_SYMBOLS:
        for family in FAMILIES:
            path = Path(
                f"configs/research/experiments/{symbol}_tick_opportunity_monthly_wfo_{family}_fullcap.yaml"
            )
            assert path.exists(), path
            cfg = _load(path)
            assert cfg["families"] == [family]
            assert family in str(cfg["out_dir"])


def test_symbol_local_reduced_configs_exist_and_keep_family() -> None:
    for symbol in ACTIVE_SYMBOLS:
        for family in FAMILIES:
            path = Path(f"configs/research/experiments/{symbol}_{family}_reduced_core_rolling.yaml")
            assert path.exists(), path
            cfg = _load(path)
            assert cfg["family_keep"] == family
            # barrier_keep must be present. select_reduced_core_regimes.py only
            # invokes the barrier parser when barrier_keep is truthy; forward-return
            # families (no barrier in their state_id) must declare barrier_keep: ''
            # to skip parsing. Omitting the key crashes selection.
            assert "barrier_keep" in cfg, f"{path}: missing barrier_keep"
            # candidate_csv must reference the family's *library* file (which mining
            # actually writes), not a family-named file.
            expected_csv = (
                "data/analysis/tick_opportunity_mining/"
                f"{symbol.upper()}_{CANDIDATE_LIBRARY[family]}_candidates.csv"
            )
            assert cfg["candidate_csv"] == expected_csv, (
                f"{path}: candidate_csv {cfg['candidate_csv']!r} != {expected_csv!r} "
                "(must point at the library candidate CSV, not a family-named one)"
            )
