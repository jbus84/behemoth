from pathlib import Path

import yaml

ACTIVE_SYMBOLS = ("eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_directional_reduced_configs_use_canonical_family_keep() -> None:
    for symbol in ACTIVE_SYMBOLS:
        path = Path(f"configs/research/experiments/{symbol}_directional_reduced_rolling.yaml")
        assert path.exists(), path
        cfg = _load(path)
        assert cfg["family_keep"] == "directional"
        assert "shock_revert" not in str(cfg)
        assert "shock_extreme_revert" not in str(cfg)


def test_directional_wfo_configs_are_family_driven() -> None:
    for symbol in ACTIVE_SYMBOLS:
        path = Path(
            f"configs/research/experiments/{symbol}_tick_opportunity_monthly_wfo_directional_fullcap.yaml"
        )
        assert path.exists(), path
        cfg = _load(path)
        assert cfg["library"] == "directional"
        assert cfg["families"] == ["directional"]


def test_dukascopy_candidate_directional_configs_exist() -> None:
    for symbol in ACTIVE_SYMBOLS:
        wfo = Path(
            "configs/research/experiments_dukascopy_candidate"
        ) / f"{symbol}_tick_opportunity_monthly_wfo_directional_fullcap.yaml"
        reduced = Path(
            "configs/research/experiments_dukascopy_candidate"
        ) / f"{symbol}_directional_reduced_core_rolling.yaml"
        assert wfo.exists(), wfo
        assert reduced.exists(), reduced
        assert _load(wfo)["families"] == ["directional"]
        assert _load(reduced)["family_keep"] == "directional"
