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
