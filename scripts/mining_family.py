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


def _frame_fingerprint(frame: pd.DataFrame) -> int:
    """Content identity for short-lived per-family caches.

    Hashes the frame's row contents together with its shape and columns.
    Two frames with identical contents share a cache entry (their
    precompute results are identical); two frames with differing contents
    never collide -- unlike an id()-based key, which silently collides when
    a later frame is allocated at a garbage-collected frame's address."""
    row_hashes = pd.util.hash_pandas_object(frame, index=True).to_numpy()
    return hash((row_hashes.tobytes(), frame.shape, tuple(frame.columns)))


_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "directional": ["directional"],
    "directional_run": ["directional_run"],
    "double_touch": ["double_touch"],
    "pullback": ["pullback"],
    "no_touch": ["no_touch"],
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

        try:
            return _oco_precompute_candidates(
                frame,
                symbol=symbol,
                horizon=int(params["horizon"]),
                barrier_pips=float(params["barrier_pips"]),
            )
        except ValueError:
            return None

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


class DoubleTouchFamily:
    name = "double_touch"

    _B_PIPS = [2.0, 4.0]
    _WINDOWS = [5, 15]

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        """Drop cached precompute results. Long-lived processes should call
        this between mining batches to avoid unbounded growth."""
        self._cache.clear()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        a_grid = _parse_floats(str(cfg["barrier_grid_pips"]))
        horizons = _parse_ints(str(cfg["horizons"]))
        grid: list[dict[str, Any]] = []
        for sweep_dir in ("up", "down"):
            for a in a_grid:
                for b in self._B_PIPS:
                    for wa in self._WINDOWS:
                        for wb in self._WINDOWS:
                            for h2 in horizons:
                                if (
                                    a <= 0.0 or b <= 0.0
                                    or wa <= 0 or wb <= 0 or h2 <= 0
                                ):
                                    raise ValueError(
                                        f"non-positive grid value: a={a} b={b} "
                                        f"wA={wa} wB={wb} h2={h2}"
                                    )
                                grid.append({
                                    "sweep_dir": sweep_dir,
                                    "a_pips": float(a),
                                    "b_pips": float(b),
                                    "window_A": int(wa),
                                    "window_B": int(wb),
                                    "horizon": int(h2),
                                })
        return grid

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _double_touch_precompute

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        try:
            result = _double_touch_precompute(
                frame,
                symbol=symbol,
                sweep_dir=str(params["sweep_dir"]),
                a_pips=float(params["a_pips"]),
                b_pips=float(params["b_pips"]),
                window_A=int(params["window_A"]),
                window_B=int(params["window_B"]),
                h2=int(params["horizon"]),
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
        sd = str(params["sweep_dir"])
        a = float(params["a_pips"])
        b = float(params["b_pips"])
        wa = int(params["window_A"])
        wb = int(params["window_B"])
        h2 = int(params["horizon"])
        return {
            "family": "double_touch",
            "state_id": (
                f"double_touch__{regime_name}__{sd}_a{a:g}_b{b:g}"
                f"_wA{wa}_wB{wb}_h{h2}"
            ),
            "regime_desc": (
                f"{regime_name};sweep={sd};a={a:g};b={b:g}"
                f";wA={wa};wB={wb};h={h2}"
            ),
            "ml_ready_target_type": "double_touch",
        }


class PullbackFamily:
    name = "pullback"

    _R_FRACS = [0.382, 0.5, 0.618]
    _WINDOWS = [5, 15]
    _WINDOW_R = 10

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        """Drop cached precompute results. Long-lived processes should call
        this between mining batches to avoid unbounded growth."""
        self._cache.clear()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        m_grid = _parse_floats(str(cfg["barrier_grid_pips"]))
        horizons = _parse_ints(str(cfg["horizons"]))
        grid: list[dict[str, Any]] = []
        for impulse_dir in ("up", "down"):
            for m in m_grid:
                for r in self._R_FRACS:
                    for wi in self._WINDOWS:
                        for wp in self._WINDOWS:
                            for h2 in horizons:
                                if (
                                    m <= 0.0 or wi <= 0 or wp <= 0 or h2 <= 0
                                    or not (0.0 < r < 1.0)
                                ):
                                    raise ValueError(
                                        f"invalid grid value: m={m} r={r} "
                                        f"wI={wi} wP={wp} h={h2}"
                                    )
                                grid.append({
                                    "impulse_dir": impulse_dir,
                                    "m_pips": float(m),
                                    "r_frac": float(r),
                                    "window_I": int(wi),
                                    "window_P": int(wp),
                                    "window_R": int(self._WINDOW_R),
                                    "horizon": int(h2),
                                })
        return grid

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _pullback_precompute

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
        if key in self._cache:
            return self._cache[key]
        try:
            result = _pullback_precompute(
                frame,
                symbol=symbol,
                impulse_dir=str(params["impulse_dir"]),
                m_pips=float(params["m_pips"]),
                r_frac=float(params["r_frac"]),
                window_I=int(params["window_I"]),
                window_P=int(params["window_P"]),
                window_R=int(params["window_R"]),
                h=int(params["horizon"]),
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
        d = str(params["impulse_dir"])
        m = float(params["m_pips"])
        r = float(params["r_frac"])
        wi = int(params["window_I"])
        wp = int(params["window_P"])
        wr = int(params["window_R"])
        h2 = int(params["horizon"])
        return {
            "family": "pullback",
            "state_id": (
                f"pullback__{regime_name}__{d}_M{m:g}_R{r:g}"
                f"_wI{wi}_wP{wp}_wR{wr}_h{h2}"
            ),
            "regime_desc": (
                f"{regime_name};impulse={d};M={m:g};R={r:g}"
                f";wI={wi};wP={wp};wR={wr};h={h2}"
            ),
            "ml_ready_target_type": "pullback",
        }


class NoTouchFamily:
    """Range-fade / sell-the-range family — the honest inverse of
    oco_first_touch. A symmetric +/-K range bet is placed at every regime
    bar: a horizon that completes without touching either barrier wins a
    fixed +K pips; a touch books the breakout continuation as a loss. Reuses
    _oco_precompute_candidates rather than adding a new engine."""

    name = "no_touch"

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        """Drop cached precompute results. Long-lived processes should call
        this between mining batches to avoid unbounded growth."""
        self._cache.clear()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_floats, _parse_ints

        barriers = _parse_floats(str(cfg["barrier_grid_pips"]))
        horizons = _parse_ints(str(cfg["horizons"]))
        grid: list[dict[str, Any]] = []
        for k in barriers:
            for h in horizons:
                if k <= 0.0 or h <= 0:
                    raise ValueError(f"non-positive grid value: k={k} h={h}")
                grid.append({"barrier_pips": float(k), "horizon": int(h)})
        return grid

    def _precompute(
        self, frame: pd.DataFrame, symbol: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        from scripts.run_tick_opportunity_mining import _oco_precompute_candidates

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
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
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=np.int64)
        # Not gated on `decided`: un-touched bars are the wins, not dropped
        # candidates. Every valid regime bar is an entry.
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        reg = np.asarray(regime_mask, dtype=bool)[i0]
        return i0[reg]

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        if "symbol" not in params:
            return np.array([], dtype=float)
        prep = self._precompute(frame, str(params["symbol"]), params)
        if not prep:
            return np.array([], dtype=float)
        i0 = np.asarray(prep["i0"], dtype=np.int64)
        decided = np.asarray(prep["decided"], dtype=bool)
        oco_gross = np.asarray(prep["gross"], dtype=float)
        k = float(params["barrier_pips"])
        # No touch -> +K win. Touch -> -(signed breakout continuation); a
        # decided entry whose continuation exit is out of bounds keeps the
        # NaN that _oco_precompute_candidates already produced.
        nt_gross = np.where(decided, -oco_gross, k)
        pos = pd.Series(np.arange(len(i0)), index=i0)
        mapped = pos.reindex(entries).to_numpy(dtype=float)
        out = np.full(len(entries), np.nan, dtype=float)
        valid = np.isfinite(mapped)
        out[valid] = nt_gross[mapped[valid].astype(np.int64)]
        return out

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        k = float(params["barrier_pips"])
        h = int(params["horizon"])
        return {
            "family": "no_touch",
            "state_id": f"no_touch__{regime_name}__K{k:g}_h{h}",
            "regime_desc": f"{regime_name};K={k:g};h={h}",
            "ml_ready_target_type": "no_touch",
        }


class OcoAsymmetricFamily:
    name = "oco_asymmetric"

    _DOWN_PIPS = [2.0, 3.0, 5.0, 8.0]
    _RR = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

    def __init__(self) -> None:
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

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

        key = (_frame_fingerprint(frame), tuple(sorted(params.items())))
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
    "double_touch": DoubleTouchFamily(),
    "pullback": PullbackFamily(),
    "no_touch": NoTouchFamily(),
}
