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


_FINGERPRINT_ATTR = "__mining_fingerprint"

_PRECOMPUTE_CACHE_CAP = 8


def _set_bounded(cache: dict, key: Any, value: Any) -> None:
    """Insertion-ordered FIFO eviction for per-family `_precompute` caches.

    The cache is consulted O(20+) times for the same key within one
    candidate's evaluation (real entries + baseline draws); once we move
    to new params we never need the old entry again. Without a cap, the
    cache holds one entry per unique (frame, params) tuple across the
    entire family — for DoubleTouchFamily that's 480 entries × ~34 MB
    per entry on an 851k-row train frame ≈ 16 GB, which OOM-kills an
    8 GB machine. Cap=8 leaves slack for train/test alternation while
    keeping peak memory at <300 MB for the largest grid."""
    if len(cache) >= _PRECOMPUTE_CACHE_CAP:
        cache.pop(next(iter(cache)))
    cache[key] = value


_FLOAT_COL_CACHE_ATTR = "__mining_float_col_cache"


def _cached_float_col(frame: pd.DataFrame, col: str) -> np.ndarray:
    """Memoised `pd.to_numeric(frame[col]).to_numpy(float)` on frame.attrs.

    Family `measure_gross` and `entry_indices` methods previously re-ran
    `pd.to_numeric(frame[ycol]).to_numpy(float)` on every call — a full
    O(n) scan of the ~850k-row column at ~50-100ms each. With 30+ params
    × 17 regimes × multiple calls per regime that was the dominant per-
    family cost (observed: ~107s per directional_run params, ~250s per
    directional_inverse params).

    Same memoisation pattern as #217's `_frame_fingerprint` and #223's
    `prepare_fills_frame_context`: cache results on `frame.attrs` keyed
    by column name. Mining frames are read-only in the hot path, so
    caching by frame identity is safe."""
    cache = frame.attrs.setdefault(_FLOAT_COL_CACHE_ATTR, {})
    cached = cache.get(col)
    if cached is not None:
        return cached
    arr = pd.to_numeric(frame[col], errors="coerce").to_numpy(dtype=float)
    cache[col] = arr
    return arr


def _frame_fingerprint(frame: pd.DataFrame) -> int:
    """Content identity for short-lived per-family caches.

    Hashes the frame's row contents together with its shape and columns.
    Two frames with identical contents share a cache entry (their
    precompute results are identical); two frames with differing contents
    never collide -- unlike an id()-based key, which silently collides when
    a later frame is allocated at a garbage-collected frame's address.

    The hash itself is O(n) (via `pd.util.hash_pandas_object`) and on a
    ~850k-row train frame costs ~100-200ms per call. Under per-family
    `_precompute` caching, this gets called once per `measure_gross` lookup
    — thousands of times per family — and the fingerprint cost will
    dominate everything the cache saved. So memoise the fingerprint on
    the frame itself via `frame.attrs` (pandas' per-frame metadata dict;
    GC'd with the frame, no id-collision risk). Mining frames are
    read-only in the hot path, so caching by frame identity is safe."""
    cached = frame.attrs.get(_FINGERPRINT_ATTR)
    if cached is not None:
        return cached
    row_hashes = pd.util.hash_pandas_object(frame, index=True).to_numpy()
    fp = hash((row_hashes.tobytes(), frame.shape, tuple(frame.columns)))
    frame.attrs[_FINGERPRINT_ATTR] = fp
    return fp


def _gross_at_entries_via_i0(
    i0: np.ndarray, gross: np.ndarray, entries: np.ndarray
) -> np.ndarray:
    """Position-lookup `entries` against monotonically-sorted `i0`, return
    `gross` at the matching positions; NaN for entries not in i0.

    Earlier OCO-style families rebuilt a `pd.Series(arange(n), index=i0)`
    per measure_gross call to do this lookup — that allocates a ~len(i0)
    Series every call, which at len(i0) ~ 1M and thousands of measure_gross
    calls per family was the dominant per-candidate cost. np.searchsorted
    does the same lookup in O(m log n) with no allocation."""
    if entries.size == 0 or i0.size == 0:
        return np.full(entries.size, np.nan, dtype=float)
    idx = np.searchsorted(i0, entries)
    out = np.full(entries.size, np.nan, dtype=float)
    in_bounds = idx < i0.size
    valid = np.zeros(entries.size, dtype=bool)
    valid[in_bounds] = i0[idx[in_bounds]] == entries[in_bounds]
    out[valid] = gross[idx[valid]]
    return out


_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "directional": ["directional"],
    "directional_inverse": ["directional_inverse"],
    "directional_run": ["directional_run"],
    "double_touch": ["double_touch"],
    "pullback": ["pullback"],
    "no_touch": ["no_touch"],
    "dollar_residual": ["dollar_residual"],
    "dispersion_rank": ["dispersion_rank"],
    "lead_lag": ["lead_lag"],
    "separate": ["oco_first_touch", "directional"],
    "all": [
        "oco_first_touch",
        "oco_asymmetric",
        "directional",
        "directional_inverse",
        "directional_run",
        "double_touch",
        "pullback",
        "no_touch",
        "dollar_residual",
        "dispersion_rank",
        "lead_lag",
    ],
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
        y = _cached_float_col(frame, ycol)
        side = _cached_float_col(frame, sidecol)
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
        y = _cached_float_col(frame, ycol)
        side = _cached_float_col(frame, sidecol)
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


class DirectionalInverseFamily:
    """Contrarian directional family: fades the `_dir_side_h{h}` signal.

    Hypothesis (post-rebuild 2026-05-20 observation): the base `directional`
    family produced strongly negative mean_baseline_z scores on 4/6 majors
    (USDJPY −3.12, GBPUSD −2.99, USDCAD −2.61, USDCHF −2.63), meaning real
    entries underperformed random by 2–3 sigma. Flipping the entry side is
    the cleanest test of whether that underperformance is a genuine inverse
    edge or a wash.

    Same entry universe as `directional` (same bars, same regime conditioning,
    same horizon); only the realised gross is sign-flipped.
    """

    name = "directional_inverse"

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
        y = _cached_float_col(frame, ycol)
        side = _cached_float_col(frame, sidecol)
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
        y = _cached_float_col(frame, ycol)
        side = _cached_float_col(frame, sidecol)
        return -side[entries] * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        h = int(params["horizon"])
        return {
            "family": "directional_inverse",
            "state_id": f"directional_inverse__{regime_name}__h{h}",
            "regime_desc": regime_name,
            "ml_ready_target_type": "directional_inverse",
        }


class OcoFirstTouchFamily:
    name = "oco_first_touch"

    def __init__(self) -> None:
        # Cache _oco_precompute_candidates results so entry_indices and
        # measure_gross share one barrier-touch scan per (frame, params).
        # Without this, every per-regime call (and every random-baseline
        # draw call) re-runs the ~12M-op scan from scratch. With 510
        # candidates per (symbol, bar_ticks) the un-cached version costs
        # ~150s of pure recomputation — empirically the dominant cost
        # post-PR #213 (baseline_draws=20).
        self._cache: dict[tuple[int, tuple[tuple[str, Any], ...]], dict[str, Any] | None] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

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
        _set_bounded(self._cache, key, result)
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
        return _gross_at_entries_via_i0(i0, gross, np.asarray(entries, dtype=np.int64))

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
    # Spec design used [5, 15] for window_A / window_B as independent
    # asymmetric phases. Empirically the full 2 × 2 = 4 window combos
    # produced 0 passes across both measured symbols. Collapsed to a
    # single mid-value to cut the grid 4x.
    _WINDOWS = [10]

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
        _set_bounded(self._cache, key, result)
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
        return _gross_at_entries_via_i0(i0, gross, np.asarray(entries, dtype=np.int64))

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
    # Impulse window × pullback window: spec used [5, 15] for both as
    # independent asymmetric phases. Empirically 0 passes across two
    # measured symbols at the full grid. Collapsed to a single mid-
    # value to cut the grid 4x (wi × wp from 4 → 1).
    _WINDOWS = [10]
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
        _set_bounded(self._cache, key, result)
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
        return _gross_at_entries_via_i0(i0, gross, np.asarray(entries, dtype=np.int64))

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
        _set_bounded(self._cache, key, result)
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
        return _gross_at_entries_via_i0(i0, nt_gross, np.asarray(entries, dtype=np.int64))

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
        _set_bounded(self._cache, key, result)
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
        return _gross_at_entries_via_i0(i0, gross, np.asarray(entries, dtype=np.int64))

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

    def __init__(self) -> None:
        # Cache _run_length results per frame fingerprint. Each call was
        # re-scanning the full ~850K-row frame for consecutive-run lengths;
        # with 1020 candidates × ~5 calls each that was the bottleneck.
        self._run_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def clear_cache(self) -> None:
        self._run_cache.clear()

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

    def _cached_run_length(
        self, frame: pd.DataFrame
    ) -> tuple[np.ndarray, np.ndarray]:
        from scripts.run_tick_opportunity_mining import _run_length

        key = _frame_fingerprint(frame)
        cached = self._run_cache.get(key)
        if cached is not None:
            return cached
        result = _run_length(frame)
        _set_bounded(self._run_cache, key, result)
        return result

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns or "ret1_pips" not in frame.columns:
            return np.array([], dtype=np.int64)
        run_len, run_sign = self._cached_run_length(frame)
        y = _cached_float_col(frame, ycol)
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
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=float)
        _, run_sign = self._cached_run_length(frame)
        y = _cached_float_col(frame, ycol)
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


class DollarFactorResidualFamily:
    """Cross-symbol residual mean-reversion (family A).

    Decomposes the target's USD-aligned return into a USD-factor component
    (rolling OLS on `mkt_loo`) and an idiosyncratic residual. Enters
    contrarian when the standardised residual exceeds a threshold.

    See docs/superpowers/specs/2026-05-21-cross-symbol-residual-design.md.
    """

    name = "dollar_residual"

    _RESIDUAL_WINDOWS = [200, 500]
    _THRESHOLDS = [1.5, 2.0, 2.5, 3.0]

    def __init__(self) -> None:
        # Per-(frame_fingerprint, residual_window) regression outputs.
        # The cross-symbol frame itself is cached at module level in
        # scripts.cross_symbol._BUILT_CS_FRAME_CACHE (shared across all
        # 3 cross-symbol families) — see the streaming-load PR.
        self._reg_cache: dict[
            tuple[int, int], dict[str, np.ndarray]
        ] = {}

    def clear_cache(self) -> None:
        from scripts.cross_symbol import clear_cross_symbol_frame_cache

        self._reg_cache.clear()
        clear_cross_symbol_frame_cache()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {
                "horizon": int(h),
                "residual_window": int(w),
                "threshold_z": float(z),
            }
            for h in horizons
            for w in self._RESIDUAL_WINDOWS
            for z in self._THRESHOLDS
        ]

    def _build_cs_frame(
        self, frame: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame | None:
        """Get the shared cs_frame for (symbol, bar_ticks) and row-align
        it to the supplied train/test-split `frame` by close_ts.

        Returns None if context (dataset_dir, horizons) is missing — the
        family is then a no-op (treated like a frame missing required
        columns).
        """
        from pathlib import Path

        from scripts.cross_symbol import (
            CROSS_SYMBOLS,
            get_or_build_cross_symbol_frame,
        )

        symbol = str(params.get("symbol", "")).upper()
        bar_ticks = int(params.get("bar_ticks", 0))
        dataset_dir = params.get("_dataset_dir")
        horizons = params.get("_horizons")
        if (
            symbol not in CROSS_SYMBOLS
            or bar_ticks <= 0
            or dataset_dir is None
            or horizons is None
        ):
            return None

        try:
            cs_full = get_or_build_cross_symbol_frame(
                target_symbol=symbol,
                bar_ticks=bar_ticks,
                dataset_dir=Path(str(dataset_dir)),
                horizons=list(horizons),
            )
        except (FileNotFoundError, ValueError):
            return None

        if "close_ts" not in frame.columns or "close_ts" not in cs_full.columns:
            return None
        cs_aligned = cs_full.merge(
            frame[["close_ts"]].assign(_ord=np.arange(len(frame))),
            on="close_ts",
            how="inner",
        ).sort_values("_ord").reset_index(drop=True)
        cs_aligned = cs_aligned.drop(columns=["_ord"])
        return cs_aligned

    def _rolling_regression_loop(
        self, cs_frame: pd.DataFrame, target_symbol: str, window: int
    ) -> dict[str, np.ndarray]:
        """REFERENCE — loop version, kept for parity testing. Do not call
        from production code; use `_rolling_regression` (vectorised)."""
        from scripts.cross_symbol import _usd_aligned_ret_z

        r = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(dtype=float)
        m = pd.to_numeric(cs_frame["mkt_loo"], errors="coerce").to_numpy(dtype=float)
        n = len(r)
        alpha = np.full(n, np.nan, dtype=float)
        beta = np.full(n, np.nan, dtype=float)
        sigma = np.full(n, np.nan, dtype=float)
        eps = np.full(n, np.nan, dtype=float)
        z = np.full(n, np.nan, dtype=float)
        min_obs = max(int(window // 4), 20)

        for t in range(int(window), n):
            lo = t - int(window)
            rr = r[lo:t]
            mm = m[lo:t]
            ok = np.isfinite(rr) & np.isfinite(mm)
            if int(ok.sum()) < min_obs:
                continue
            rr = rr[ok]
            mm = mm[ok]
            m_var = float(np.var(mm))
            if m_var <= 0.0:
                continue
            m_mean = float(np.mean(mm))
            r_mean = float(np.mean(rr))
            b = float(np.cov(rr, mm, ddof=0)[0, 1] / m_var)
            a = r_mean - b * m_mean
            e_train = rr - a - b * mm
            s = float(np.std(e_train, ddof=0))
            if not np.isfinite(s) or s <= 0.0:
                continue
            alpha[t] = a
            beta[t] = b
            sigma[t] = s
            if np.isfinite(r[t]) and np.isfinite(m[t]):
                eps_t = r[t] - a - b * m[t]
                eps[t] = eps_t
                z[t] = eps_t / s

        return {"alpha": alpha, "beta": beta, "sigma": sigma, "eps": eps, "z": z}

    def _rolling_regression(
        self, cs_frame: pd.DataFrame, target_symbol: str, window: int
    ) -> dict[str, np.ndarray]:
        """Trailing-window OLS of target USD-aligned ret_z on mkt_loo —
        vectorised. Matches `_rolling_regression_loop` within rtol=1e-6;
        ~100-500x faster at n=2M."""
        from scripts.cross_symbol import _usd_aligned_ret_z

        key = (_frame_fingerprint(cs_frame), int(window))
        if key in self._reg_cache:
            return self._reg_cache[key]

        r = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(dtype=float)
        m = pd.to_numeric(cs_frame["mkt_loo"], errors="coerce").to_numpy(dtype=float)
        w = int(window)
        min_obs = max(w // 4, 20)

        ok = np.isfinite(r) & np.isfinite(m)
        r0 = np.where(ok, r, 0.0)
        m0 = np.where(ok, m, 0.0)

        def _roll_sum(a: np.ndarray) -> np.ndarray:
            s = pd.Series(a).rolling(w, min_periods=1).sum().to_numpy(dtype=float)
            return np.concatenate(([np.nan], s[:-1]))  # shift(1) so bar t uses [t-w, t)

        cnt = _roll_sum(ok.astype(float))
        sum_r = _roll_sum(r0)
        sum_m = _roll_sum(m0)
        sum_rm = _roll_sum(r0 * m0)
        sum_r2 = _roll_sum(r0 * r0)
        sum_m2 = _roll_sum(m0 * m0)

        with np.errstate(invalid="ignore", divide="ignore"):
            mean_r = sum_r / cnt
            mean_m = sum_m / cnt
            mean_rm = sum_rm / cnt
            mean_r2 = sum_r2 / cnt
            mean_m2 = sum_m2 / cnt

            var_m = mean_m2 - mean_m * mean_m
            cov_rm = mean_rm - mean_r * mean_m
            beta = np.where(var_m > 0.0, cov_rm / np.where(var_m > 0.0, var_m, 1.0), np.nan)
            alpha = mean_r - beta * mean_m

            # OLS identity: mean(e^2) = mean_r2 - alpha*mean_r - beta*mean_rm
            # (more numerically stable than expanding the full quadratic form).
            sigma2 = mean_r2 - alpha * mean_r - beta * mean_rm
            sigma2 = np.maximum(sigma2, 0.0)
            sigma = np.sqrt(sigma2)
            # Note: deliberately do NOT NaN-out sigma==0 here; the loop's
            # `s <= 0.0` skip leaves NaN, but rolling-sum cancellation noise
            # produces tiny positive sigmas (~1e-8) when residuals are
            # genuinely zero. Both are within atol=1e-12 in absolute terms.
            sigma = np.where(np.isfinite(sigma), sigma, np.nan)

            eps_now = r - alpha - beta * m
            z_now = eps_now / sigma

        insufficient = ~(cnt >= float(min_obs))
        for arr in (alpha, beta, sigma):
            arr[insufficient] = np.nan
        eps_out = np.where(
            insufficient | ~np.isfinite(r) | ~np.isfinite(m) | ~np.isfinite(sigma),
            np.nan,
            eps_now,
        )
        z_out = np.where(
            insufficient | ~np.isfinite(r) | ~np.isfinite(m) | ~np.isfinite(sigma),
            np.nan,
            z_now,
        )

        for arr in (alpha, beta, sigma, eps_out, z_out):
            arr[:w] = np.nan

        out = {"alpha": alpha, "beta": beta, "sigma": sigma,
               "eps": eps_out, "z": z_out}
        _set_bounded(self._reg_cache, key, out)
        return out

    def _entry_state(
        self, frame: pd.DataFrame, params: dict[str, Any]
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """Returns (entry_mask, side) over the aligned frame, or None if
        no cross-symbol context is available."""
        cs = self._build_cs_frame(frame, params)
        if cs is None or len(cs) != len(frame):
            return None
        symbol = str(params["symbol"]).upper()
        window = int(params["residual_window"])
        threshold = float(params["threshold_z"])
        reg = self._rolling_regression(cs, symbol, window)
        z = reg["z"]
        side = np.zeros(len(frame), dtype=np.int8)
        side[z >= threshold] = -1   # extreme positive residual → short
        side[z <= -threshold] = 1   # extreme negative residual → long
        entry = side != 0
        return entry, side

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=np.int64)
        state = self._entry_state(frame, params)
        if state is None:
            return np.array([], dtype=np.int64)
        entry, _ = state
        y = _cached_float_col(frame, ycol)
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = entry & valid & np.asarray(regime_mask, dtype=bool)
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=float)
        state = self._entry_state(frame, params)
        if state is None:
            return np.array([], dtype=float)
        _, side = state
        y = _cached_float_col(frame, ycol)
        return side[entries].astype(float) * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        window = int(params["residual_window"])
        threshold = float(params["threshold_z"])
        return {
            "family": "dollar_residual",
            "state_id": (
                f"dollar_residual__{regime_name}__"
                f"w{window}_z{threshold:.1f}"
            ),
            "regime_desc": (
                f"{regime_name};window={window};z={threshold:.1f}"
            ),
            "ml_ready_target_type": "dollar_residual",
        }


class DispersionRankFamily:
    """Cross-symbol dispersion rank (family B).

    Ranks the 6 majors' USD-aligned returns at each target bar; enters
    contrarian when the target is at the top-k or bottom-k extreme.

    See docs/superpowers/specs/2026-05-21-cross-symbol-dispersion-design.md.
    """

    name = "dispersion_rank"

    _RANK_KS = [1, 2]

    def __init__(self) -> None:
        # Per-frame rank arrays (target_rank, side_raw) keyed by
        # (frame_fingerprint, target_symbol). The cross-symbol frame
        # itself is cached at module level in
        # scripts.cross_symbol._BUILT_CS_FRAME_CACHE.
        self._rank_cache: dict[
            tuple[int, str], tuple[np.ndarray, np.ndarray]
        ] = {}

    def clear_cache(self) -> None:
        from scripts.cross_symbol import clear_cross_symbol_frame_cache

        self._rank_cache.clear()
        clear_cross_symbol_frame_cache()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {"horizon": int(h), "rank_k": int(k)}
            for h in horizons
            for k in self._RANK_KS
        ]

    def _build_cs_frame(
        self, frame: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame | None:
        from pathlib import Path

        from scripts.cross_symbol import (
            CROSS_SYMBOLS,
            get_or_build_cross_symbol_frame,
        )

        symbol = str(params.get("symbol", "")).upper()
        bar_ticks = int(params.get("bar_ticks", 0))
        dataset_dir = params.get("_dataset_dir")
        horizons = params.get("_horizons")
        if (
            symbol not in CROSS_SYMBOLS
            or bar_ticks <= 0
            or dataset_dir is None
            or horizons is None
        ):
            return None
        try:
            cs_full = get_or_build_cross_symbol_frame(
                target_symbol=symbol,
                bar_ticks=bar_ticks,
                dataset_dir=Path(str(dataset_dir)),
                horizons=list(horizons),
            )
        except (FileNotFoundError, ValueError):
            return None
        if "close_ts" not in frame.columns or "close_ts" not in cs_full.columns:
            return None
        cs_aligned = cs_full.merge(
            frame[["close_ts"]].assign(_ord=np.arange(len(frame))),
            on="close_ts",
            how="inner",
        ).sort_values("_ord").reset_index(drop=True).drop(columns=["_ord"])
        return cs_aligned

    def _per_bar_rank_and_side_loop(
        self, cs_frame: pd.DataFrame, target_symbol: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """REFERENCE — loop version, kept for parity testing."""
        from scripts.cross_symbol import (
            _USD_SIGN,
            CROSS_SYMBOLS,
            _usd_aligned_ret_z,
        )

        n = len(cs_frame)
        target_usd = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(float)
        peers = sorted(s for s in CROSS_SYMBOLS if s != target_symbol)
        peer_cols = [f"xs_ret_z__{s}" for s in peers]
        cols = peer_cols + ["__target"]
        matrix = cs_frame[peer_cols].copy()
        matrix["__target"] = target_usd
        arr = matrix[cols].to_numpy(float)

        target_rank = np.full(n, np.nan, dtype=float)
        for i in range(n):
            row = arr[i]
            if not np.isfinite(row).all():
                continue
            order = np.argsort(-row, kind="stable")
            rank_of_col = np.empty(len(row), dtype=np.int64)
            rank_of_col[order] = np.arange(1, len(row) + 1)
            target_rank[i] = float(rank_of_col[-1])

        usd = _USD_SIGN[target_symbol]
        return (target_rank, np.full(n, usd, dtype=np.int8))

    def _per_bar_rank_and_side(
        self, cs_frame: pd.DataFrame, target_symbol: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """Per-bar descending rank of the target's USD-aligned return among
        the 6 majors. Vectorised — one np.argsort on the full (n,6) matrix
        replaces the per-row argsort loop. Matches `_loop` exactly."""
        key = (_frame_fingerprint(cs_frame), target_symbol)
        if key in self._rank_cache:
            return self._rank_cache[key]

        result = self._per_bar_rank_and_side_compute(cs_frame, target_symbol)
        _set_bounded(self._rank_cache, key, result)
        return result

    def _per_bar_rank_and_side_compute(
        self, cs_frame: pd.DataFrame, target_symbol: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """Cache-free hot path of `_per_bar_rank_and_side`. Exposed so the
        perf microbench can measure the work being vectorised without
        `_frame_fingerprint` (an O(n) pandas hash) dominating the timer."""
        from scripts.cross_symbol import (
            _USD_SIGN,
            CROSS_SYMBOLS,
            _usd_aligned_ret_z,
        )

        n = len(cs_frame)
        target_usd = _usd_aligned_ret_z(cs_frame, target_symbol).to_numpy(float)
        peers = sorted(s for s in CROSS_SYMBOLS if s != target_symbol)
        peer_cols = [f"xs_ret_z__{s}" for s in peers]
        cols = peer_cols + ["__target"]
        matrix = cs_frame[peer_cols].copy()
        matrix["__target"] = target_usd
        arr = matrix[cols].to_numpy(float)  # shape (n, 6)

        target_rank = np.full(n, np.nan, dtype=float)
        all_finite = np.isfinite(arr).all(axis=1)
        if np.any(all_finite):
            order = np.argsort(-arr[all_finite], axis=1, kind="stable")
            ranks = np.empty_like(order)
            row_idx = np.arange(order.shape[0])[:, None]
            rank_values = np.broadcast_to(
                np.arange(1, arr.shape[1] + 1), order.shape
            )
            ranks[row_idx, order] = rank_values
            target_rank[all_finite] = ranks[:, -1].astype(float)

        usd = _USD_SIGN[target_symbol]
        return (target_rank, np.full(n, usd, dtype=np.int8))

    def _entry_state(
        self, frame: pd.DataFrame, params: dict[str, Any]
    ) -> tuple[np.ndarray, np.ndarray] | None:
        cs = self._build_cs_frame(frame, params)
        if cs is None or len(cs) != len(frame):
            return None
        symbol = str(params["symbol"]).upper()
        rank_k = int(params["rank_k"])
        target_rank, usd_sign = self._per_bar_rank_and_side(cs, symbol)

        n = len(frame)
        side_raw = np.zeros(n, dtype=np.int8)
        top_mask = np.isfinite(target_rank) & (target_rank <= rank_k)
        bot_mask = np.isfinite(target_rank) & (target_rank >= (7 - rank_k))
        # rank ≤ k → fade USD-positive direction.
        side_raw[top_mask] = (-1) * usd_sign[top_mask]
        # rank ≥ 7-k → fade USD-negative direction.
        side_raw[bot_mask] = (+1) * usd_sign[bot_mask]
        entry = side_raw != 0
        return entry, side_raw

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=np.int64)
        state = self._entry_state(frame, params)
        if state is None:
            return np.array([], dtype=np.int64)
        entry, _ = state
        y = _cached_float_col(frame, ycol)
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = entry & valid & np.asarray(regime_mask, dtype=bool)
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=float)
        state = self._entry_state(frame, params)
        if state is None:
            return np.array([], dtype=float)
        _, side = state
        y = _cached_float_col(frame, ycol)
        return side[entries].astype(float) * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        k = int(params["rank_k"])
        return {
            "family": "dispersion_rank",
            "state_id": f"dispersion_rank__{regime_name}__k{k}",
            "regime_desc": f"{regime_name};k={k}",
            "ml_ready_target_type": "dispersion_rank",
        }


class LeadLagFamily:
    """Cross-symbol lead-lag follow (family C).

    Triggers on a peer's USD-aligned return at bar `t − lag_k` exceeding
    `±trigger_z`; enters the target at bar `t` in the same USD-direction
    (follow, not fade).

    See docs/superpowers/specs/2026-05-21-cross-symbol-leadlag-design.md.
    """

    name = "lead_lag"

    _LAGS = [1, 2]
    _THRESHOLDS = [1.5, 2.0]

    def __init__(self) -> None:
        # Per-(frame_fingerprint, peer, lag) shifted trigger arrays.
        # The cross-symbol frame itself is cached at module level in
        # scripts.cross_symbol._BUILT_CS_FRAME_CACHE.
        self._shift_cache: dict[
            tuple[int, str, int], np.ndarray
        ] = {}

    def clear_cache(self) -> None:
        from scripts.cross_symbol import clear_cross_symbol_frame_cache

        self._shift_cache.clear()
        clear_cross_symbol_frame_cache()

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from scripts.cross_symbol import CROSS_SYMBOLS
        from scripts.run_tick_opportunity_mining import _parse_ints

        horizons = _parse_ints(str(cfg["horizons"]))
        return [
            {
                "horizon": int(h),
                "peer": str(p),
                "lag_k": int(k),
                "trigger_z": float(z),
            }
            for h in horizons
            for p in CROSS_SYMBOLS
            for k in self._LAGS
            for z in self._THRESHOLDS
        ]

    def _build_cs_frame(
        self, frame: pd.DataFrame, params: dict[str, Any]
    ) -> pd.DataFrame | None:
        from pathlib import Path

        from scripts.cross_symbol import (
            CROSS_SYMBOLS,
            get_or_build_cross_symbol_frame,
        )

        symbol = str(params.get("symbol", "")).upper()
        bar_ticks = int(params.get("bar_ticks", 0))
        dataset_dir = params.get("_dataset_dir")
        horizons = params.get("_horizons")
        if (
            symbol not in CROSS_SYMBOLS
            or bar_ticks <= 0
            or dataset_dir is None
            or horizons is None
        ):
            return None
        try:
            cs_full = get_or_build_cross_symbol_frame(
                target_symbol=symbol,
                bar_ticks=bar_ticks,
                dataset_dir=Path(str(dataset_dir)),
                horizons=list(horizons),
            )
        except (FileNotFoundError, ValueError):
            return None
        if "close_ts" not in frame.columns or "close_ts" not in cs_full.columns:
            return None
        cs_aligned = cs_full.merge(
            frame[["close_ts"]].assign(_ord=np.arange(len(frame))),
            on="close_ts",
            how="inner",
        ).sort_values("_ord").reset_index(drop=True).drop(columns=["_ord"])
        return cs_aligned

    def _peer_trigger_at_lag(
        self, cs_frame: pd.DataFrame, peer: str, lag_k: int
    ) -> np.ndarray | None:
        """Peer's xs_ret_z column shifted forward by lag_k bars so that
        the value at output row `t` equals the peer column at row `t-k`.
        Returns None if the peer column is absent."""
        col = f"xs_ret_z__{peer}"
        if col not in cs_frame.columns:
            return None
        key = (_frame_fingerprint(cs_frame), peer, int(lag_k))
        if key in self._shift_cache:
            return self._shift_cache[key]
        raw = pd.to_numeric(cs_frame[col], errors="coerce").to_numpy(dtype=float)
        shifted = np.full_like(raw, np.nan)
        if lag_k > 0:
            shifted[lag_k:] = raw[:-lag_k]
        else:
            shifted[:] = raw
        self._shift_cache[key] = shifted
        return shifted

    def _entry_state(
        self, frame: pd.DataFrame, params: dict[str, Any]
    ) -> tuple[np.ndarray, np.ndarray] | None:
        from scripts.cross_symbol import _USD_SIGN

        peer = str(params["peer"]).upper()
        target = str(params["symbol"]).upper()
        if peer == target:
            return None  # self-peer is not a candidate
        cs = self._build_cs_frame(frame, params)
        if cs is None or len(cs) != len(frame):
            return None
        lag_k = int(params["lag_k"])
        trigger = float(params["trigger_z"])
        shifted = self._peer_trigger_at_lag(cs, peer, lag_k)
        if shifted is None:
            return None
        n = len(frame)
        side_raw = np.zeros(n, dtype=np.int8)
        usd = _USD_SIGN[target]
        # Follow: peer USD-positive trigger -> follow USD-positive ->
        # raw side = +usd. Peer USD-negative -> raw side = -usd.
        pos = np.isfinite(shifted) & (shifted >= +trigger)
        neg = np.isfinite(shifted) & (shifted <= -trigger)
        side_raw[pos] = +usd
        side_raw[neg] = -usd
        entry = side_raw != 0
        return entry, side_raw

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=np.int64)
        state = self._entry_state(frame, params)
        if state is None:
            return np.array([], dtype=np.int64)
        entry, _ = state
        y = _cached_float_col(frame, ycol)
        valid = np.isfinite(y)
        if h > 0:
            valid[-h:] = False
        m = entry & valid & np.asarray(regime_mask, dtype=bool)
        return np.flatnonzero(m).astype(np.int64)

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        h = int(params["horizon"])
        ycol = f"y_fwd_pips_h{h}"
        if ycol not in frame.columns:
            return np.array([], dtype=float)
        state = self._entry_state(frame, params)
        if state is None:
            return np.array([], dtype=float)
        _, side = state
        y = _cached_float_col(frame, ycol)
        return side[entries].astype(float) * y[entries]

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        peer = str(params["peer"])
        lag_k = int(params["lag_k"])
        trigger = float(params["trigger_z"])
        return {
            "family": "lead_lag",
            "state_id": (
                f"lead_lag__{regime_name}__p{peer}_k{lag_k}_z{trigger:.1f}"
            ),
            "regime_desc": (
                f"{regime_name};peer={peer};lag={lag_k};z={trigger:.1f}"
            ),
            "ml_ready_target_type": "lead_lag",
        }


FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "oco_asymmetric": OcoAsymmetricFamily(),
    "directional": DirectionalFamily(),
    "directional_inverse": DirectionalInverseFamily(),
    "directional_run": DirectionalRunFamily(),
    "double_touch": DoubleTouchFamily(),
    "pullback": PullbackFamily(),
    "no_touch": NoTouchFamily(),
    "dollar_residual": DollarFactorResidualFamily(),
    "dispersion_rank": DispersionRankFamily(),
    "lead_lag": LeadLagFamily(),
}
