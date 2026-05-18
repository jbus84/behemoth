"""Candidate-family registry for tick-opportunity mining.

Each family supplies its own entry trigger, outcome measurement, parameter
grid, and candidate metadata. The core mining loop in
run_tick_opportunity_mining.py iterates the registry rather than branching on
a hardcoded library type.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class MiningFamily(Protocol):
    name: str

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Family-specific parameter combinations to mine (e.g. barrier
        widths). Returns at least one dict; an empty dict means no extra
        axis."""
        ...

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Look-ahead-free integer entry bar indices for one regime mask and
        one param combo."""
        ...

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Gross pips realised per entry. MUST accept any entry index array
        (used for both real entries and random-baseline draws)."""
        ...

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """family / state_id / regime_desc / ml_ready_target_type for the
        candidate row."""
        ...


_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "directional": ["directional"],
    "directional_run": ["directional_run"],
    "separate": ["oco_first_touch", "directional"],
}


def resolve_families(library_type: str) -> list[str]:
    """Map a legacy library_type string to a list of family names."""
    key = str(library_type).strip().lower()
    if key not in _LIBRARY_TYPE_ALIASES:
        raise ValueError(
            f"unknown library_type {library_type!r}; "
            f"expected one of {sorted(_LIBRARY_TYPE_ALIASES)}"
        )
    return list(_LIBRARY_TYPE_ALIASES[key])


class DirectionalFamily:
    name = "directional"

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        return [{"horizon": h} for h in _parse_ints(str(cfg["horizons"]))]

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        sidecol = f"_dir_side_h{h}"
        if ycol not in frame.columns or sidecol not in frame.columns:
            return np.array([], dtype=np.int64)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        side = frame[sidecol].to_numpy()
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = valid & np.asarray(regime_mask, dtype=bool) & (side != 0)
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        sidecol = f"_dir_side_h{h}"
        if ycol not in frame.columns or sidecol not in frame.columns:
            return np.array([], dtype=float)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        side = frame[sidecol].to_numpy().astype(float)
        return side[entries] * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        h = int(params["horizon"])
        return {
            "family": "directional",
            "state_id": f"directional__{regime_name}__h{h}",
            "regime_desc": regime_name,
            "ml_ready_target_type": "directional",
        }


class OcoFirstTouchFamily:
    name = "oco_first_touch"

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        barriers = _parse_floats(str(cfg["barrier_grid_pips"]))
        return [
            {"horizon": int(h), "barrier_pips": float(k)}
            for h in horizons
            for k in barriers
        ]

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _oco_precompute_candidates

        key = (id(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        try:
            result = _oco_precompute_candidates(
                frame,
                symbol=symbol,
                horizon=int(params["horizon"]),
                barrier_pips=float(params["barrier_pips"]),
            )
        except ValueError:
            result = None
        self._cache[key] = result
        return result

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=np.int64)
        symbol = str(params["symbol"])
        prep = self._precompute(frame, symbol, params)
        if not prep:
            return np.array([], dtype=np.int64)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        decided = np.asarray(prep["decided"], dtype=bool)
        reg = np.asarray(regime_mask, dtype=bool)[i0]
        return i0[decided & reg]

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=float)
        symbol = str(params["symbol"])
        prep = self._precompute(frame, symbol, params)
        if not prep:
            return np.array([], dtype=float)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        gross = np.asarray(prep["gross"], dtype=float)
        pos = pd.Series(np.arange(len(i0)), index=i0)
        mapped = pos.reindex(entries).to_numpy(dtype=float)
        out = np.full(len(entries), np.nan, dtype=float)
        valid = np.isfinite(mapped)
        out[valid] = gross[mapped[valid].astype(np.int64)]
        return out

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        k = float(params["barrier_pips"])
        return {
            "family": "oco_first_touch",
            "state_id": f"oco_first_touch__{regime_name}__k{int(round(k))}",
            "regime_desc": f"{regime_name};barrier={k:.1f}",
            "ml_ready_target_type": "oco_expand",
        }


class OcoAsymmetricFamily:
    name = "oco_asymmetric"

    # Spec-defined grid: standard stop distances and reward ratios
    _DOWN_PIPS = [2.0, 3.0, 5.0, 8.0]
    _RR = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {"horizon": int(h), "down_pips": float(d), "rr": float(r)}
            for h in horizons
            for d in self._DOWN_PIPS
            for r in self._RR
        ]

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _oco_asymmetric_precompute

        key = (id(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        down = float(params["down_pips"])
        rr = float(params["rr"])
        up = down * rr
        if down <= 0.0 or up <= 0.0:
            raise ValueError(f"non-positive barrier: down={down} up={up}")
        try:
            result = _oco_asymmetric_precompute(
                frame,
                symbol=symbol,
                horizon=int(params["horizon"]),
                up_pips=up,
                down_pips=down,
            )
        except ValueError:
            result = None
        self._cache[key] = result
        return result

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=np.int64)
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=np.int64)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        decided = np.asarray(prep["decided"], dtype=bool)
        reg = np.asarray(regime_mask, dtype=bool)[i0]
        return i0[decided & reg]

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=float)
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=float)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        gross = np.asarray(prep["gross"], dtype=float)
        pos = pd.Series(np.arange(len(i0)), index=i0)
        mapped = pos.reindex(entries).to_numpy(dtype=float)
        out = np.full(len(entries), np.nan, dtype=float)
        valid = np.isfinite(mapped)
        out[valid] = gross[mapped[valid].astype(np.int64)]
        return out

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        down = float(params["down_pips"])
        rr = float(params["rr"])
        return {
            "family": "oco_asymmetric",
            "state_id": f"oco_asymmetric__{regime_name}__d{down:g}_rr{rr:g}",
            "regime_desc": f"{regime_name};down={down:g};rr={rr:g}",
            "ml_ready_target_type": "oco_asymmetric",
        }


class DirectionalRunFamily:
    name = "directional_run"

    _BUCKETS = ["2", "3", "4", "5", "6+"]
    _BETS = ["continuation", "reversion"]

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {"horizon": int(h), "run_bucket": b, "bet": bet}
            for h in horizons
            for b in self._BUCKETS
            for bet in self._BETS
        ]

    def _bucket_mask(self, run_len: np.ndarray, bucket: str) -> np.ndarray:
        if bucket == "6+":
            return run_len >= 6
        if bucket in {"2", "3", "4", "5"}:
            return run_len == int(bucket)
        raise ValueError(f"unknown run_bucket {bucket!r}")

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        from scripts.run_tick_opportunity_mining import _run_length

        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns or "ret1_pips" not in frame.columns:
            return np.array([], dtype=np.int64)
        run_len, run_sign = _run_length(frame)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = (
            valid
            & np.asarray(regime_mask, dtype=bool)
            & self._bucket_mask(run_len, str(params["run_bucket"]))
            & (run_sign != 0)
        )
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        from scripts.run_tick_opportunity_mining import _run_length

        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=float)
        _, run_sign = _run_length(frame)
        y = pd.to_numeric(frame[ycol], errors="coerce").to_numpy(dtype=float)
        side = run_sign.astype(float)
        bet = str(params["bet"])
        if bet == "reversion":
            side = -side
        elif bet != "continuation":
            raise ValueError(f"unknown bet {bet!r}")
        return side[entries] * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        bucket = str(params["run_bucket"])
        bet = str(params["bet"])
        return {
            "family": "directional_run",
            "state_id": f"directional_run__{regime_name}__n{bucket}_{bet}",
            "regime_desc": f"{regime_name};run={bucket};bet={bet}",
            "ml_ready_target_type": "directional_run",
        }


FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "oco_asymmetric": OcoAsymmetricFamily(),
    "directional": DirectionalFamily(),
    "directional_run": DirectionalRunFamily(),
}
