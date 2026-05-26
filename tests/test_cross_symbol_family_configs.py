from pathlib import Path

import yaml

ACTIVE_SYMBOLS = ("eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad")
CROSS_SYMBOL_FAMILIES = ("dollar_residual", "dispersion_rank", "lead_lag")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_cross_symbol_wfo_configs_exist_and_declare_scope() -> None:
    for symbol in ACTIVE_SYMBOLS:
        for family in CROSS_SYMBOL_FAMILIES:
            path = Path(
                f"configs/research/experiments/{symbol}_tick_opportunity_monthly_wfo_{family}_fullcap.yaml"
            )
            assert path.exists(), path
            cfg = _load(path)
            assert cfg["families"] == [family]
            assert cfg["cross_symbol_scope"]["symbols"] == [
                "EURUSD",
                "GBPUSD",
                "USDJPY",
                "USDCHF",
                "AUDUSD",
                "USDCAD",
            ]
            assert cfg["cross_symbol_scope"]["alignment"] == "close_ts_inner_join"


def test_cross_symbol_reduced_configs_exist() -> None:
    for symbol in ACTIVE_SYMBOLS:
        for family in CROSS_SYMBOL_FAMILIES:
            path = Path(f"configs/research/experiments/{symbol}_{family}_reduced_core_rolling.yaml")
            assert path.exists(), path
            assert _load(path)["family_keep"] == family
