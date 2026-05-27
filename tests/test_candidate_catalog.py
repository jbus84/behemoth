from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.behemoth.core.bundle_paths import BundlePaths
from src.behemoth.core.candidate_catalog import CandidateCatalog
from src.behemoth.core.historical_registry import HistoricalCandidateRegistry, HistoricalLockEntry
from src.behemoth.core.registry import CandidateRegistry, CandidateSpec


def test_candidate_spec_has_family_field() -> None:
    spec = CandidateSpec(
        symbol="EURUSD",
        bar_ticks=100,
        horizon=4,
        barrier_pips=10.0,
        candidate_uid="test__all__k1",
        family="directional",
    )
    assert spec.family == "directional"


def _candidate(symbol: str = "EURUSD", bar_ticks: int = 100, family: str = "oco_first_touch") -> CandidateSpec:
    return CandidateSpec(
        symbol=symbol,
        bar_ticks=bar_ticks,
        horizon=6,
        barrier_pips=2.0,
        candidate_uid=f"library|{symbol}|{bar_ticks}|h6|b2",
        family=family,
    )


def _create_bundle_paths_for_test(tmp_dir: Path, symbol: str = "EURUSD", model_month: str = "2026-04") -> BundlePaths:
    """Create a minimal BundlePaths for testing."""
    import hashlib

    # Create model files
    models_dir = tmp_dir / "models"
    models_dir.mkdir(exist_ok=True)
    cbm_file = models_dir / f"{symbol}_model_{model_month}.cbm"
    json_file = models_dir / f"{symbol}_model_{model_month}.json"
    cbm_file.write_bytes(b"fake-cbm-data")
    json_file.write_text('{"threshold": 0.5}')

    # Create predictions file
    pred_file = tmp_dir / f"{symbol}_oco_locked_predictions.parquet"
    pred_file.write_bytes(b"fake-parquet-data")

    # Compute sha256s
    cbm_sha = hashlib.sha256(cbm_file.read_bytes()).hexdigest()
    json_sha = hashlib.sha256(json_file.read_bytes()).hexdigest()
    pred_sha = hashlib.sha256(pred_file.read_bytes()).hexdigest()

    lock = tmp_dir / f"{symbol}_oco_first_touch_live_lock.json"
    lock_data = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {
            "month": model_month,
            "dir_relpath": ".",
            "family": "oco_first_touch",
        },
        "artifacts": {
            "predictions": {"path": "predictions.parquet", "sha256": pred_sha},
            "model_cbm": {"path": f"models/{cbm_file.name}", "sha256": cbm_sha},
            "model_threshold_json": {"path": f"models/{json_file.name}", "sha256": json_sha},
        },
        "deployability": {"live_deployable": True, "model_month": model_month},
        "locked_runtime": {"production_cap_pips": 1.5},
        "state_universe": {"rows": []},
    }
    lock.write_text(json.dumps(lock_data))

    # Rename predictions file to match lock reference
    (tmp_dir / "predictions.parquet").write_bytes(b"fake-parquet-data")
    pred_file.unlink()

    return BundlePaths.from_lock(lock)


def test_candidate_catalog_resolves_live_contract() -> None:
    with TemporaryDirectory() as tmp_dir:
        bundle_paths = _create_bundle_paths_for_test(Path(tmp_dir), "EURUSD", "2026-04")

        registry = CandidateRegistry()
        registry._candidates_by_symbol["EURUSD"] = [_candidate(bar_ticks=200)]
        registry._caps_by_symbol_family[("EURUSD", "oco_first_touch")] = 1.5
        registry._bundle_paths_by_symbol_family[("EURUSD", "oco_first_touch")] = bundle_paths

        catalog = CandidateCatalog(
            live_registry=registry,
            historical_registry=None,
            historical_mode=False,
        )

        contract = catalog.resolve_contract("eurusd", datetime(2026, 5, 1, tzinfo=timezone.utc))

        assert contract.source == "live"
        assert contract.cache_key == "EURUSD"
        assert contract.model_month == "2026-04"
        assert contract.cap_pips == 1.5
        assert catalog.active_bar_ticks("EURUSD") == [200]


def test_candidate_registry_requires_exact_family_bindings() -> None:
    registry = CandidateRegistry()

    with pytest.raises(KeyError, match="No cap_pips binding for EURUSD family directional"):
        registry.get_cap_pips("EURUSD", "directional")

    with pytest.raises(KeyError, match="No bundle paths binding for EURUSD family directional"):
        registry.get_bundle_paths("EURUSD", "directional")


def test_candidate_catalog_rejects_missing_month() -> None:
    with TemporaryDirectory() as tmp_dir:
        bundle_paths = _create_bundle_paths_for_test(Path(tmp_dir), "EURUSD", "2026-03")

        historical = HistoricalCandidateRegistry()
        historical._entries[("EURUSD", "2026-03", "oco_first_touch")] = HistoricalLockEntry(
            symbol="EURUSD",
            month="2026-03",
            family="oco_first_touch",
            lock_path="locks/2026-03/EURUSD_oco_first_touch_live_lock.json",
            candidates=[_candidate()],
            cap_pips=1.2,
            bundle_paths=bundle_paths,
        )
        catalog = CandidateCatalog(
            live_registry=None,
            historical_registry=historical,
            historical_mode=True,
            missing_month_policy="nearest_previous",
            latest_loaded_month=lambda _symbol: "2026-03",
        )

        with pytest.raises(KeyError, match="No historical lock for EURUSD month 2026-04 family oco_first_touch"):
            catalog.resolve_contract("EURUSD", datetime(2026, 4, 2, tzinfo=timezone.utc), family="oco_first_touch")

        assert catalog.active_bar_ticks("EURUSD", family="oco_first_touch") == [100]


def test_candidate_catalog_reports_missing_historical_months() -> None:
    catalog = CandidateCatalog(
        live_registry=None,
        historical_registry=HistoricalCandidateRegistry(),
        historical_mode=True,
    )

    with pytest.raises(KeyError, match="No historical lock for EURUSD month 2026-04 family oco_first_touch"):
        catalog.resolve_contract("EURUSD", datetime(2026, 4, 2, tzinfo=timezone.utc), family="oco_first_touch")


def test_registry_loads_multiple_families() -> None:
    import hashlib

    with TemporaryDirectory() as tmp:
        t = Path(tmp)
        for family in ("oco_first_touch", "directional"):
            lock = t / f"eurusd_{family}_live_lock.json"
            models_dir = t / "models"
            models_dir.mkdir(exist_ok=True)
            cbm = models_dir / f"EURUSD_{family}_model_2026-04.cbm"
            thr = models_dir / f"EURUSD_{family}_model_2026-04.json"
            cbm.write_bytes(b"cbm")
            thr.write_text('{"t":1}')
            preds = t / f"eurusd_{family}_locked_predictions.parquet"
            states_csv = t / f"eurusd_{family}_allowed_states.csv"
            preds.write_bytes(b"preds")
            states_csv.write_text("state\na\n")
            payload = {
                "schema_version": 3,
                "symbol": "EURUSD",
                "bundle": {"month": "2026-04", "dir_relpath": ".", "family": family},
                "deployability": {"live_deployable": True, "model_month": "2026-04"},
                "locked_runtime": {"production_cap_pips": 1.2},
                "state_universe": {
                    "rows": [
                        {
                            "state_id": f"{family}__all__k1",
                            "symbol": "EURUSD",
                            "bar_ticks": 100,
                            "horizon": 4,
                            "barrier_pips": 10.0,
                        }
                    ]
                },
                "artifacts": {
                    "predictions": {"path": preds.name, "sha256": hashlib.sha256(b"preds").hexdigest()},
                    "allowed_states_csv": {"path": states_csv.name, "sha256": hashlib.sha256(states_csv.read_bytes()).hexdigest()},
                    "model_cbm": {"path": f"models/{cbm.name}", "sha256": hashlib.sha256(b"cbm").hexdigest()},
                    "model_threshold_json": {"path": f"models/{thr.name}", "sha256": hashlib.sha256(thr.read_bytes()).hexdigest()},
                },
            }
            lock.write_text(json.dumps(payload))

        reg = CandidateRegistry.load(lock_dir=t)
        cands = reg.get_candidates("EURUSD")
        families = {c.family for c in cands}
        assert families == {"oco_first_touch", "directional"}


def test_candidate_catalog_returns_all_family_candidates() -> None:
    import hashlib

    with TemporaryDirectory() as tmp:
        t = Path(tmp)
        for family in ("oco_first_touch", "directional"):
            lock = t / f"eurusd_{family}_live_lock.json"
            models_dir = t / "models"
            models_dir.mkdir(exist_ok=True)
            cbm = models_dir / f"EURUSD_{family}_model_2026-04.cbm"
            thr = models_dir / f"EURUSD_{family}_model_2026-04.json"
            cbm.write_bytes(b"cbm")
            thr.write_text('{"t":1}')
            preds = t / f"eurusd_{family}_locked_predictions.parquet"
            states_csv = t / f"eurusd_{family}_allowed_states.csv"
            preds.write_bytes(b"preds")
            states_csv.write_text("state\na\n")
            payload = {
                "schema_version": 3,
                "symbol": "EURUSD",
                "bundle": {"month": "2026-04", "dir_relpath": ".", "family": family},
                "deployability": {"live_deployable": True, "model_month": "2026-04"},
                "locked_runtime": {"production_cap_pips": 1.2},
                "state_universe": {
                    "rows": [
                        {
                            "state_id": f"{family}__all__k1",
                            "symbol": "EURUSD",
                            "bar_ticks": 100,
                            "horizon": 4,
                            "barrier_pips": 10.0,
                        }
                    ]
                },
                "artifacts": {
                    "predictions": {"path": preds.name, "sha256": hashlib.sha256(b"preds").hexdigest()},
                    "allowed_states_csv": {"path": states_csv.name, "sha256": hashlib.sha256(states_csv.read_bytes()).hexdigest()},
                    "model_cbm": {"path": f"models/{cbm.name}", "sha256": hashlib.sha256(b"cbm").hexdigest()},
                    "model_threshold_json": {"path": f"models/{thr.name}", "sha256": hashlib.sha256(thr.read_bytes()).hexdigest()},
                },
            }
            lock.write_text(json.dumps(payload))

        reg = CandidateRegistry.load(lock_dir=t)
        catalog = CandidateCatalog(live_registry=reg, historical_registry=None, historical_mode=False)
        contract = catalog.resolve_contract("EURUSD", datetime(2026, 5, 1, tzinfo=timezone.utc))
        families = {c.family for c in contract.candidates}
        assert families == {"oco_first_touch", "directional"}
