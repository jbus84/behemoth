# Live Threshold Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only diagnostic that classifies live Rolling Threshold behavior as `PARITY_BREACH`, `THRESHOLD_DRIFT`, `RUNTIME_VARIANCE`, `MODEL_VALIDITY_CONCERN`, or `INCONCLUSIVE`.

**Architecture:** Add a focused Python diagnostics module that reads Runtime State through DuckDB queries, reconstructs threshold pools, compares live Feature Set rows to recomputation from Tick Bars, decomposes distribution shifts, runs offline estimator comparisons, and emits Markdown/CSV/JSON evidence. Keep production runtime code unchanged; expose the feature through a thin script under `scripts/`.

**Tech Stack:** Python, DuckDB, pandas, numpy, pytest, existing `src.behemoth.core.features.compute_feature_matrix_from_bars`.

---

## File Structure

- Create `src/behemoth/diagnostics/__init__.py`: package marker for diagnostic helpers.
- Create `src/behemoth/diagnostics/live_threshold.py`: all diagnostic dataclasses, DuckDB queries, parity checks, classification rules, artifact writers, and report generation.
- Create `scripts/diagnose_live_thresholds.py`: CLI wrapper that checkpoints the API if requested, opens the DuckDB file read-only, runs the diagnostic, and writes artifacts.
- Create `tests/test_live_threshold_diagnostics.py`: unit tests for threshold pool reconstruction, source classification, Feature Set parity, estimator gating, and final classification.
- No production API, StateManager, model, or Java files should change in this plan.

---

### Task 1: Add Diagnostic Domain Models And Classification Rules

**Files:**
- Create: `src/behemoth/diagnostics/__init__.py`
- Create: `src/behemoth/diagnostics/live_threshold.py`
- Test: `tests/test_live_threshold_diagnostics.py`

- [ ] **Step 1: Write failing classification tests**

Add this to `tests/test_live_threshold_diagnostics.py`:

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_classifies_parity_breach_before_threshold_drift() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=False,
            feature_parity_checked=True,
            current_pool_lag_detected=True,
            live_distribution_unusual=True,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "PARITY_BREACH"


def test_classifies_threshold_drift_when_parity_passes_and_pool_lags() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=True,
            feature_parity_checked=True,
            current_pool_lag_detected=True,
            live_distribution_unusual=True,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "THRESHOLD_DRIFT"


def test_classifies_inconclusive_when_required_evidence_is_missing() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=False,
            threshold_replay_matches=False,
            feature_parity_passed=False,
            feature_parity_checked=False,
            current_pool_lag_detected=False,
            live_distribution_unusual=False,
            model_validity_concern=False,
            evidence_missing=True,
        )
    )

    assert result == "INCONCLUSIVE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.behemoth.diagnostics'`.

- [ ] **Step 3: Add minimal diagnostic models and classifier**

Create `src/behemoth/diagnostics/__init__.py`:

```python
"""Diagnostics for local runtime and governance evidence."""
```

Create `src/behemoth/diagnostics/live_threshold.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import pandas as pd

DiagnosticClassification = Literal[
    "PARITY_BREACH",
    "THRESHOLD_DRIFT",
    "RUNTIME_VARIANCE",
    "MODEL_VALIDITY_CONCERN",
    "INCONCLUSIVE",
]


@dataclass(frozen=True)
class DiagnosticInputs:
    threshold_pool_complete: bool
    threshold_replay_matches: bool
    feature_parity_passed: bool
    feature_parity_checked: bool
    current_pool_lag_detected: bool
    live_distribution_unusual: bool
    model_validity_concern: bool
    evidence_missing: bool


@dataclass(frozen=True)
class LiveThresholdConfig:
    symbol: str
    run_id: str
    live_run_id: str
    lookback_days: int
    execution_quantile: float
    min_history: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    out_dir: Path


def classify_diagnostic(inputs: DiagnosticInputs) -> DiagnosticClassification:
    if inputs.evidence_missing:
        return "INCONCLUSIVE"
    if not inputs.threshold_pool_complete or not inputs.feature_parity_checked:
        return "INCONCLUSIVE"
    if (not inputs.feature_parity_passed) or (not inputs.threshold_replay_matches):
        return "PARITY_BREACH"
    if inputs.current_pool_lag_detected:
        return "THRESHOLD_DRIFT"
    if inputs.model_validity_concern:
        return "MODEL_VALIDITY_CONCERN"
    if inputs.live_distribution_unusual:
        return "RUNTIME_VARIANCE"
    return "RUNTIME_VARIANCE"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/__init__.py src/behemoth/diagnostics/live_threshold.py tests/test_live_threshold_diagnostics.py
git commit -m "feat: add live threshold diagnostic classifier"
```

---

### Task 2: Implement Rolling Threshold Pool Audit

**Files:**
- Modify: `src/behemoth/diagnostics/live_threshold.py`
- Modify: `tests/test_live_threshold_diagnostics.py`

- [ ] **Step 1: Write failing threshold pool tests**

Append to `tests/test_live_threshold_diagnostics.py`:

```python
import duckdb
import pytest


def _audit_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
        """
    )
    rows = [
        ("2026-05-01T00:00:00Z", "2026-05-01T00:00:00Z", "EURUSD", "oco|EURUSD|100|h6|s1", 0.70, 0.60, "{}", "2026-04", "threshold_seed"),
        ("2026-05-04T00:00:00Z", "2026-05-04T00:00:00Z", "EURUSD", "oco|EURUSD|100|h6|s1", 0.80, 0.60, "{}", "2026-04", "warmup"),
        ("2026-05-08T00:00:00Z", "2026-05-08T00:00:00Z", "EURUSD", "oco|EURUSD|100|h6|s1", 0.50, 0.60, "{}", "2026-04", "jforex_live"),
    ]
    con.executemany("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return con


def test_threshold_pool_audit_reconstructs_quantile_and_sources() -> None:
    from src.behemoth.diagnostics.live_threshold import audit_threshold_pool

    con = _audit_db()
    try:
        detail, summary = audit_threshold_pool(
            con,
            symbol="EURUSD",
            execution_quantile=0.9,
            lookback_days=20,
            min_history=1,
            as_of=pd.Timestamp("2026-05-09T00:00:00Z"),
            live_run_id="jforex_live",
        )
    finally:
        con.close()

    assert len(detail) == 3
    assert set(detail["source_period"]) == {"seed", "warmup", "live"}
    assert summary.loc[0, "pool_rows"] == 3
    assert summary.loc[0, "live_rows"] == 1
    assert summary.loc[0, "replayed_threshold"] == pytest.approx(0.78)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_threshold_pool_audit_reconstructs_quantile_and_sources
```

Expected: FAIL with `ImportError` or `AttributeError` for `audit_threshold_pool`.

- [ ] **Step 3: Implement threshold pool audit**

Append these functions to `src/behemoth/diagnostics/live_threshold.py`:

```python
def _source_period(run_id: object, live_run_id: str) -> str:
    value = "" if run_id is None or pd.isna(run_id) else str(run_id).strip().lower()
    if value == "threshold_seed":
        return "seed"
    if value == "warmup":
        return "warmup"
    if value == live_run_id.lower():
        return "live"
    if "live" in value:
        return "live"
    if "warmup" in value:
        return "warmup"
    if "seed" in value:
        return "seed"
    return "other"


def audit_threshold_pool(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    execution_quantile: float,
    lookback_days: int,
    min_history: int,
    as_of: pd.Timestamp,
    live_run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    as_of_utc = pd.Timestamp(as_of).tz_convert("UTC") if pd.Timestamp(as_of).tzinfo else pd.Timestamp(as_of).tz_localize("UTC")
    cutoff = as_of_utc - pd.Timedelta(days=int(lookback_days))
    detail = con.execute(
        """
        SELECT
            close_ts,
            upper(symbol) AS symbol,
            candidate_uid,
            pred_prob,
            threshold,
            model_month,
            run_id
        FROM audit_logs
        WHERE upper(symbol) = upper(?)
          AND close_ts >= ?
          AND close_ts <= ?
          AND pred_prob IS NOT NULL
        ORDER BY candidate_uid, close_ts, run_id
        """,
        [symbol.upper(), cutoff.to_pydatetime(), as_of_utc.to_pydatetime()],
    ).fetchdf()
    if detail.empty:
        columns = [
            "symbol",
            "candidate_uid",
            "pool_rows",
            "seed_rows",
            "warmup_rows",
            "live_rows",
            "other_rows",
            "p50",
            "p75",
            "p90",
            "p95",
            "replayed_threshold",
            "min_history_met",
            "first_close_ts",
            "last_close_ts",
        ]
        return detail.assign(source_period=pd.Series(dtype="object")), pd.DataFrame(columns=columns)

    detail["source_period"] = detail["run_id"].map(lambda value: _source_period(value, live_run_id))
    detail["pred_prob"] = pd.to_numeric(detail["pred_prob"], errors="coerce")
    rows: list[dict[str, object]] = []
    for (sym, candidate_uid), group in detail.groupby(["symbol", "candidate_uid"], dropna=False):
        probs = group["pred_prob"].dropna()
        source_counts = group["source_period"].value_counts()
        rows.append(
            {
                "symbol": sym,
                "candidate_uid": candidate_uid,
                "pool_rows": int(len(probs)),
                "seed_rows": int(source_counts.get("seed", 0)),
                "warmup_rows": int(source_counts.get("warmup", 0)),
                "live_rows": int(source_counts.get("live", 0)),
                "other_rows": int(source_counts.get("other", 0)),
                "p50": float(probs.quantile(0.50)) if len(probs) else np.nan,
                "p75": float(probs.quantile(0.75)) if len(probs) else np.nan,
                "p90": float(probs.quantile(0.90)) if len(probs) else np.nan,
                "p95": float(probs.quantile(0.95)) if len(probs) else np.nan,
                "replayed_threshold": float(probs.quantile(float(execution_quantile))) if len(probs) else np.nan,
                "min_history_met": bool(len(probs) >= int(min_history)),
                "first_close_ts": group["close_ts"].min(),
                "last_close_ts": group["close_ts"].max(),
            }
        )
    return detail, pd.DataFrame(rows).sort_values(["symbol", "candidate_uid"]).reset_index(drop=True)
```

- [ ] **Step 4: Run threshold pool tests**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_threshold_pool_audit_reconstructs_quantile_and_sources
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_threshold.py tests/test_live_threshold_diagnostics.py
git commit -m "feat: audit live rolling threshold pools"
```

---

### Task 3: Implement Feature Set Parity From Runtime Tick Bars

**Files:**
- Modify: `src/behemoth/diagnostics/live_threshold.py`
- Modify: `tests/test_live_threshold_diagnostics.py`

- [ ] **Step 1: Write failing Feature Set parity tests**

Append to `tests/test_live_threshold_diagnostics.py`:

```python
import json


def test_feature_parity_reports_mismatched_feature_value() -> None:
    from src.behemoth.diagnostics.live_threshold import compare_feature_parity

    live = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "features_json": json.dumps({"range_pips": 8.0, "cost_est_pips": 1.0}),
            }
        ]
    )
    recomputed = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "range_pips": 9.0,
                "cost_est_pips": 1.0,
            }
        ]
    )

    result = compare_feature_parity(
        live,
        recomputed,
        feature_columns=["range_pips", "cost_est_pips"],
        tolerance=1e-9,
    )

    assert result.loc[0, "feature"] == "range_pips"
    assert result.loc[0, "status"] == "MISMATCH"
    assert result.loc[0, "abs_diff"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_feature_parity_reports_mismatched_feature_value
```

Expected: FAIL because `compare_feature_parity` is missing.

- [ ] **Step 3: Implement Feature Set parity comparison**

Append to `src/behemoth/diagnostics/live_threshold.py`:

```python
def _parse_features_json(value: object) -> dict[str, float]:
    import json

    if value is None or pd.isna(value):
        return {}
    try:
        raw = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    out: dict[str, float] = {}
    for key, item in raw.items():
        try:
            out[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return out


def compare_feature_parity(
    live_features: pd.DataFrame,
    recomputed_features: pd.DataFrame,
    *,
    feature_columns: list[str],
    tolerance: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if live_features.empty:
        return pd.DataFrame(
            columns=[
                "close_ts",
                "candidate_uid",
                "feature",
                "live_value",
                "recomputed_value",
                "abs_diff",
                "status",
            ]
        )

    live_rows = live_features.copy()
    parsed = live_rows["features_json"].map(_parse_features_json)
    for feature in feature_columns:
        live_rows[feature] = parsed.map(lambda payload: payload.get(feature, np.nan))

    merged = live_rows.merge(
        recomputed_features[["close_ts", "candidate_uid", *feature_columns]],
        on=["close_ts", "candidate_uid"],
        how="outer",
        suffixes=("_live", "_recomputed"),
        indicator=True,
    )
    for _, row in merged.iterrows():
        for feature in feature_columns:
            live_value = row.get(f"{feature}_live", np.nan)
            recomputed_value = row.get(f"{feature}_recomputed", np.nan)
            if pd.isna(live_value) or pd.isna(recomputed_value):
                status = "MISSING"
                abs_diff = np.nan
            else:
                abs_diff = abs(float(live_value) - float(recomputed_value))
                status = "PASS" if abs_diff <= float(tolerance) else "MISMATCH"
            if status != "PASS":
                rows.append(
                    {
                        "close_ts": row.get("close_ts"),
                        "candidate_uid": row.get("candidate_uid"),
                        "feature": feature,
                        "live_value": live_value,
                        "recomputed_value": recomputed_value,
                        "abs_diff": abs_diff,
                        "status": status,
                    }
                )
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run Feature Set parity test**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_feature_parity_reports_mismatched_feature_value
```

Expected: PASS.

- [ ] **Step 5: Add runtime Feature Set recomputation helper test**

Append to `tests/test_live_threshold_diagnostics.py`:

```python
def test_recompute_features_from_runtime_bars_uses_candidate_uid_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.behemoth.diagnostics import live_threshold as module

    bars = pd.DataFrame(
        {
            "ts": pd.date_range("2026-05-08T00:00:00Z", periods=2, freq="100s", tz="UTC"),
            "close_ts": pd.date_range("2026-05-08T00:01:39Z", periods=2, freq="100s", tz="UTC"),
            "open_bid": [1.0, 1.1],
            "high_bid": [1.2, 1.3],
            "low_bid": [0.9, 1.0],
            "close_bid": [1.15, 1.25],
            "spread": [0.0002, 0.0002],
            "tick_volume": [100, 100],
            "hl_first": [1.0, -1.0],
            "hl_pos_frac": [0.4, 0.6],
            "high_ask": [1.2002, 1.3002],
            "close_ask": [1.1502, 1.2502],
        }
    )

    def fake_compute(df: pd.DataFrame, **kwargs):
        assert kwargs["symbol"] == "EURUSD"
        assert kwargs["bar_ticks"] == 100
        assert kwargs["horizon"] == 6
        assert kwargs["barrier_pips"] == 2.0
        return pd.DataFrame({"range_pips": [8.0, 9.0], "cost_est_pips": [1.0, 1.1]})

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_compute)

    out = module.recompute_features_from_runtime_bars(
        bars,
        symbol="EURUSD",
        candidate_uid="oco|EURUSD|100|h6|2",
        feature_columns=["range_pips", "cost_est_pips"],
    )

    assert list(out["candidate_uid"].unique()) == ["oco|EURUSD|100|h6|2"]
    assert float(out.iloc[-1]["range_pips"]) == pytest.approx(9.0)
```

- [ ] **Step 6: Implement runtime recomputation helper**

Add imports near the top of `src/behemoth/diagnostics/live_threshold.py`:

```python
from src.behemoth.core.features import compute_feature_matrix_from_bars
```

Append:

```python
def _parse_canonical_uid(candidate_uid: str) -> tuple[int, int, float]:
    parts = str(candidate_uid).split("|")
    if len(parts) < 5:
        raise ValueError(f"candidate_uid is not canonical: {candidate_uid}")
    bar_ticks = int(parts[2])
    horizon = int(parts[3].removeprefix("h"))
    barrier_pips = float(parts[4])
    return bar_ticks, horizon, barrier_pips


def recompute_features_from_runtime_bars(
    bars: pd.DataFrame,
    *,
    symbol: str,
    candidate_uid: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    bar_ticks, horizon, barrier_pips = _parse_canonical_uid(candidate_uid)
    frame = bars.rename(columns={"ts": "timestamp"}).copy()
    matrix = compute_feature_matrix_from_bars(
        frame,
        symbol=symbol.upper(),
        bar_ticks=bar_ticks,
        horizon=horizon,
        barrier_pips=barrier_pips,
    )
    if matrix is None or matrix.empty:
        return pd.DataFrame(columns=["close_ts", "candidate_uid", *feature_columns])
    out = matrix.loc[:, feature_columns].copy()
    out["close_ts"] = pd.to_datetime(frame.loc[matrix.index, "close_ts"], utc=True).to_numpy()
    out["candidate_uid"] = candidate_uid
    return out[["close_ts", "candidate_uid", *feature_columns]]


def load_live_feature_rows(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    live_run_id: str,
) -> pd.DataFrame:
    try:
        return con.execute(
            """
            SELECT
                close_ts,
                upper(symbol) AS symbol,
                candidate_uid,
                features_json
            FROM audit_logs
            WHERE upper(symbol) = upper(?)
              AND close_ts >= ?
              AND close_ts <= ?
              AND lower(coalesce(run_id, '')) = lower(?)
              AND coalesce(features_json, '') <> ''
            ORDER BY close_ts, candidate_uid
            """,
            [
                symbol.upper(),
                pd.Timestamp(start_ts).to_pydatetime(),
                pd.Timestamp(end_ts).to_pydatetime(),
                live_run_id,
            ],
        ).fetchdf()
    except Exception:
        return pd.DataFrame(columns=["close_ts", "symbol", "candidate_uid", "features_json"])


def load_runtime_bars(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    bar_ticks: int,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> pd.DataFrame:
    try:
        return con.execute(
            """
            SELECT
                ts,
                close_ts,
                open_bid,
                high_bid,
                low_bid,
                close_bid,
                spread,
                tick_volume,
                hl_first,
                hl_pos_frac,
                high_ask,
                close_ask
            FROM tick_bars
            WHERE upper(symbol) = upper(?)
              AND bar_ticks = ?
              AND close_ts >= ?
              AND close_ts <= ?
            ORDER BY close_ts
            """,
            [
                symbol.upper(),
                int(bar_ticks),
                pd.Timestamp(start_ts).to_pydatetime(),
                pd.Timestamp(end_ts).to_pydatetime(),
            ],
        ).fetchdf()
    except Exception:
        return pd.DataFrame()
```

- [ ] **Step 7: Run Feature Set tests**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_feature_parity_reports_mismatched_feature_value tests/test_live_threshold_diagnostics.py::test_recompute_features_from_runtime_bars_uses_candidate_uid_fields
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/behemoth/diagnostics/live_threshold.py tests/test_live_threshold_diagnostics.py
git commit -m "feat: compare live feature parity"
```

---

### Task 4: Implement Distribution Decomposition And Estimator Bake-Off

**Files:**
- Modify: `src/behemoth/diagnostics/live_threshold.py`
- Modify: `tests/test_live_threshold_diagnostics.py`

- [ ] **Step 1: Write failing decomposition and estimator tests**

Append to `tests/test_live_threshold_diagnostics.py`:

```python
def test_distribution_decomposition_flags_live_q90_drop() -> None:
    from src.behemoth.diagnostics.live_threshold import summarize_distribution_shift

    df = pd.DataFrame(
        {
            "period": ["history"] * 5 + ["live"] * 5,
            "symbol": ["EURUSD"] * 10,
            "candidate_uid": ["s1"] * 10,
            "pred_prob": [0.70, 0.72, 0.75, 0.80, 0.82, 0.50, 0.55, 0.58, 0.60, 0.62],
            "range_pips": [9.0, 9.5, 10.0, 10.5, 11.0, 7.5, 7.7, 8.0, 8.2, 8.3],
        }
    )

    summary = summarize_distribution_shift(df, value_columns=["pred_prob", "range_pips"])

    pred_row = summary[(summary["symbol"] == "EURUSD") & (summary["metric"] == "pred_prob")].iloc[0]
    assert pred_row["history_q90"] > pred_row["live_q90"]
    assert pred_row["q90_delta_live_minus_history"] < 0


def test_estimator_bakeoff_keeps_current_and_weighted_quantiles() -> None:
    from src.behemoth.diagnostics.live_threshold import run_threshold_estimator_bakeoff

    pool = pd.DataFrame(
        {
            "close_ts": pd.date_range("2026-05-01", periods=6, freq="D", tz="UTC"),
            "candidate_uid": ["s1"] * 6,
            "pred_prob": [0.90, 0.85, 0.80, 0.70, 0.60, 0.50],
            "source_period": ["seed", "seed", "warmup", "warmup", "live", "live"],
        }
    )

    out = run_threshold_estimator_bakeoff(
        pool,
        execution_quantile=0.9,
        as_of=pd.Timestamp("2026-05-08T00:00:00Z"),
    )

    assert set(out["estimator"]) == {"current_equal_weight", "short_7d_equal_weight", "recency_weighted_half_life_3d", "seed_decay_25pct"}
    assert out.loc[out["estimator"] == "seed_decay_25pct", "threshold"].notna().all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_distribution_decomposition_flags_live_q90_drop tests/test_live_threshold_diagnostics.py::test_estimator_bakeoff_keeps_current_and_weighted_quantiles
```

Expected: FAIL because the functions are missing.

- [ ] **Step 3: Implement distribution and estimator helpers**

Append to `src/behemoth/diagnostics/live_threshold.py`:

```python
def summarize_distribution_shift(
    observations: pd.DataFrame,
    *,
    value_columns: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (symbol, candidate_uid), group in observations.groupby(["symbol", "candidate_uid"], dropna=False):
        history = group[group["period"] == "history"]
        live = group[group["period"] == "live"]
        for metric in value_columns:
            hist_values = pd.to_numeric(history[metric], errors="coerce").dropna()
            live_values = pd.to_numeric(live[metric], errors="coerce").dropna()
            rows.append(
                {
                    "symbol": symbol,
                    "candidate_uid": candidate_uid,
                    "metric": metric,
                    "history_rows": int(len(hist_values)),
                    "live_rows": int(len(live_values)),
                    "history_q50": float(hist_values.quantile(0.50)) if len(hist_values) else np.nan,
                    "history_q90": float(hist_values.quantile(0.90)) if len(hist_values) else np.nan,
                    "live_q50": float(live_values.quantile(0.50)) if len(live_values) else np.nan,
                    "live_q90": float(live_values.quantile(0.90)) if len(live_values) else np.nan,
                    "q90_delta_live_minus_history": (
                        float(live_values.quantile(0.90) - hist_values.quantile(0.90))
                        if len(hist_values) and len(live_values)
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values = values[mask]
    weights = weights[mask]
    if len(values) == 0:
        return np.nan
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    cutoff = float(q) * cumulative[-1]
    return float(sorted_values[np.searchsorted(cumulative, cutoff, side="left")])


def run_threshold_estimator_bakeoff(
    threshold_pool: pd.DataFrame,
    *,
    execution_quantile: float,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    if threshold_pool.empty:
        return pd.DataFrame(columns=["candidate_uid", "estimator", "threshold", "rows"])
    as_of_utc = pd.Timestamp(as_of).tz_convert("UTC") if pd.Timestamp(as_of).tzinfo else pd.Timestamp(as_of).tz_localize("UTC")
    pool = threshold_pool.copy()
    pool["close_ts"] = pd.to_datetime(pool["close_ts"], utc=True)
    pool["pred_prob"] = pd.to_numeric(pool["pred_prob"], errors="coerce")
    rows: list[dict[str, object]] = []
    for candidate_uid, group in pool.groupby("candidate_uid", dropna=False):
        values = group["pred_prob"].dropna()
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "current_equal_weight",
                "threshold": float(values.quantile(float(execution_quantile))) if len(values) else np.nan,
                "rows": int(len(values)),
            }
        )
        short = group[group["close_ts"] >= as_of_utc - pd.Timedelta(days=7)]["pred_prob"].dropna()
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "short_7d_equal_weight",
                "threshold": float(short.quantile(float(execution_quantile))) if len(short) else np.nan,
                "rows": int(len(short)),
            }
        )
        age_days = (as_of_utc - group["close_ts"]).dt.total_seconds().to_numpy(dtype=float) / 86400.0
        weights = np.power(0.5, age_days / 3.0)
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "recency_weighted_half_life_3d",
                "threshold": _weighted_quantile(group["pred_prob"].to_numpy(dtype=float), weights, float(execution_quantile)),
                "rows": int(group["pred_prob"].notna().sum()),
            }
        )
        seed_decay_weights = np.where(group["source_period"].astype(str).eq("seed"), 0.25, 1.0)
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "seed_decay_25pct",
                "threshold": _weighted_quantile(group["pred_prob"].to_numpy(dtype=float), seed_decay_weights.astype(float), float(execution_quantile)),
                "rows": int(group["pred_prob"].notna().sum()),
            }
        )
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run decomposition and estimator tests**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_distribution_decomposition_flags_live_q90_drop tests/test_live_threshold_diagnostics.py::test_estimator_bakeoff_keeps_current_and_weighted_quantiles
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_threshold.py tests/test_live_threshold_diagnostics.py
git commit -m "feat: compare live threshold estimators"
```

---

### Task 5: Build End-To-End Diagnostic Runner And Artifact Writers

**Files:**
- Modify: `src/behemoth/diagnostics/live_threshold.py`
- Create: `scripts/diagnose_live_thresholds.py`
- Modify: `tests/test_live_threshold_diagnostics.py`

- [ ] **Step 1: Write failing report artifact test**

Append to `tests/test_live_threshold_diagnostics.py`:

```python
def test_run_diagnostic_writes_summary_and_report(tmp_path: Path) -> None:
    from src.behemoth.diagnostics.live_threshold import LiveThresholdConfig, run_live_threshold_diagnostic

    con = _audit_db()
    try:
        config = LiveThresholdConfig(
            symbol="EURUSD",
            run_id="unit_test_run",
            live_run_id="jforex_live",
            lookback_days=20,
            execution_quantile=0.9,
            min_history=1,
            start_ts=pd.Timestamp("2026-05-01T00:00:00Z"),
            end_ts=pd.Timestamp("2026-05-09T00:00:00Z"),
            out_dir=tmp_path,
        )
        result = run_live_threshold_diagnostic(con, config)
    finally:
        con.close()

    assert result["classification"] in {"THRESHOLD_DRIFT", "RUNTIME_VARIANCE", "INCONCLUSIVE"}
    assert (tmp_path / "unit_test_run_summary.json").exists()
    assert (tmp_path / "unit_test_run_report.md").exists()
    assert (tmp_path / "unit_test_run_threshold_pool.csv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_run_diagnostic_writes_summary_and_report
```

Expected: FAIL because `run_live_threshold_diagnostic` is missing.

- [ ] **Step 3: Implement artifact writing and runner**

Append to `src/behemoth/diagnostics/live_threshold.py`:

```python
def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _build_report(
    *,
    config: LiveThresholdConfig,
    classification: DiagnosticClassification,
    threshold_summary: pd.DataFrame,
    estimator_summary: pd.DataFrame,
) -> str:
    lines = [
        "# Live Threshold Diagnostic Report",
        "",
        f"- run_id: `{config.run_id}`",
        f"- symbol: `{config.symbol.upper()}`",
        f"- classification: `{classification}`",
        f"- period: `{config.start_ts}` to `{config.end_ts}`",
        "",
        "## Threshold Pool",
        "",
        _markdown_table(threshold_summary),
        "",
        "## Threshold Estimators",
        "",
        _markdown_table(estimator_summary),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def run_live_threshold_diagnostic(
    con: duckdb.DuckDBPyConnection,
    config: LiveThresholdConfig,
) -> dict[str, object]:
    detail, threshold_summary = audit_threshold_pool(
        con,
        symbol=config.symbol,
        execution_quantile=config.execution_quantile,
        lookback_days=config.lookback_days,
        min_history=config.min_history,
        as_of=config.end_ts,
        live_run_id=config.live_run_id,
    )
    threshold_pool_complete = not threshold_summary.empty and bool(threshold_summary["min_history_met"].all())
    feature_columns = [
        "cost_est_pips",
        "range_pips",
        "ret_abs_z",
        "vel_abs_cost_units_h1",
        "spread_z",
        "tick_rate_z",
        "hl_first",
        "hl_first_mean_24",
        "hl_pos_frac_mean_24",
    ]
    live_feature_rows = load_live_feature_rows(
        con,
        symbol=config.symbol,
        start_ts=config.start_ts,
        end_ts=config.end_ts,
        live_run_id=config.live_run_id,
    )
    recomputed_parts: list[pd.DataFrame] = []
    for candidate_uid in sorted(live_feature_rows["candidate_uid"].dropna().unique()):
        try:
            bar_ticks, _horizon, _barrier_pips = _parse_canonical_uid(str(candidate_uid))
        except ValueError:
            continue
        bars = load_runtime_bars(
            con,
            symbol=config.symbol,
            bar_ticks=bar_ticks,
            start_ts=config.start_ts - pd.Timedelta(days=2),
            end_ts=config.end_ts,
        )
        if bars.empty:
            continue
        recomputed_parts.append(
            recompute_features_from_runtime_bars(
                bars,
                symbol=config.symbol,
                candidate_uid=str(candidate_uid),
                feature_columns=feature_columns,
            )
        )
    recomputed_features = (
        pd.concat(recomputed_parts, ignore_index=True)
        if recomputed_parts
        else pd.DataFrame(columns=["close_ts", "candidate_uid", *feature_columns])
    )
    feature_parity = compare_feature_parity(
        live_feature_rows,
        recomputed_features,
        feature_columns=feature_columns,
        tolerance=1e-9,
    )
    feature_parity_checked = bool((not live_feature_rows.empty) and (not recomputed_features.empty))
    feature_parity_passed = bool(feature_parity_checked and feature_parity.empty)
    live_rows = int(threshold_summary["live_rows"].sum()) if not threshold_summary.empty else 0
    pool_rows = int(threshold_summary["pool_rows"].sum()) if not threshold_summary.empty else 0
    seed_warmup_rows = (
        int((threshold_summary["seed_rows"] + threshold_summary["warmup_rows"]).sum())
        if not threshold_summary.empty
        else 0
    )
    lag_detected = bool(live_rows > 0 and seed_warmup_rows > live_rows * 5)
    estimator_summary = (
        run_threshold_estimator_bakeoff(
            detail,
            execution_quantile=config.execution_quantile,
            as_of=config.end_ts,
        )
        if threshold_pool_complete and feature_parity_passed
        else pd.DataFrame(columns=["candidate_uid", "estimator", "threshold", "rows"])
    )
    inputs = DiagnosticInputs(
        threshold_pool_complete=threshold_pool_complete,
        threshold_replay_matches=threshold_pool_complete,
        feature_parity_passed=feature_parity_passed,
        feature_parity_checked=feature_parity_checked,
        current_pool_lag_detected=lag_detected,
        live_distribution_unusual=False,
        model_validity_concern=False,
        evidence_missing=(not threshold_pool_complete) or (not feature_parity_checked),
    )
    classification = classify_diagnostic(inputs)
    summary = {
        "classification": classification,
        "symbol": config.symbol.upper(),
        "run_id": config.run_id,
        "pool_rows": pool_rows,
        "live_rows": live_rows,
        "seed_warmup_rows": seed_warmup_rows,
        "threshold_pool_complete": threshold_pool_complete,
        "feature_parity_checked": feature_parity_checked,
        "feature_parity_passed": feature_parity_passed,
        "current_pool_lag_detected": lag_detected,
    }
    prefix = config.out_dir / config.run_id
    _write_csv(prefix.with_name(prefix.name + "_threshold_pool.csv"), detail)
    _write_csv(prefix.with_name(prefix.name + "_threshold_summary.csv"), threshold_summary)
    _write_csv(prefix.with_name(prefix.name + "_feature_parity.csv"), feature_parity)
    _write_csv(prefix.with_name(prefix.name + "_threshold_estimators.csv"), estimator_summary)
    _write_json(prefix.with_name(prefix.name + "_summary.json"), summary)
    prefix.with_name(prefix.name + "_report.md").write_text(
        _build_report(
            config=config,
            classification=classification,
            threshold_summary=threshold_summary,
            estimator_summary=estimator_summary,
        ),
        encoding="utf-8",
    )
    return summary
```

- [ ] **Step 4: Add CLI script**

Create `scripts/diagnose_live_thresholds.py`:

```python
#!/usr/bin/env python3
"""Diagnose live Rolling Threshold behavior from local Runtime State."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behemoth.diagnostics.live_threshold import (  # noqa: E402
    LiveThresholdConfig,
    run_live_threshold_diagnostic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose live Rolling Threshold behavior")
    parser.add_argument("--db", required=True, help="Path to live_state.db")
    parser.add_argument("--symbol", required=True, help="Symbol to diagnose, such as EURUSD")
    parser.add_argument("--run-id", required=True, help="Diagnostic run id used for output filenames")
    parser.add_argument("--live-run-id", default="jforex_live", help="Runtime run_id used for live audit rows")
    parser.add_argument("--start-ts", required=True, help="Inclusive diagnostic start timestamp")
    parser.add_argument("--end-ts", required=True, help="Inclusive diagnostic end timestamp")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--execution-quantile", type=float, default=0.9)
    parser.add_argument("--min-history", type=int, default=300)
    parser.add_argument("--out-dir", default="data/analysis/live_threshold_diagnostics")
    parser.add_argument("--api", default="", help="Optional API base URL to checkpoint before reading")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.api:
        requests.get(f"{args.api.rstrip('/')}/state/checkpoint", timeout=5).raise_for_status()
    config = LiveThresholdConfig(
        symbol=str(args.symbol).upper(),
        run_id=str(args.run_id),
        live_run_id=str(args.live_run_id),
        lookback_days=int(args.lookback_days),
        execution_quantile=float(args.execution_quantile),
        min_history=int(args.min_history),
        start_ts=pd.Timestamp(args.start_ts),
        end_ts=pd.Timestamp(args.end_ts),
        out_dir=Path(args.out_dir),
    )
    con = duckdb.connect(str(args.db), read_only=True)
    try:
        summary = run_live_threshold_diagnostic(con, config)
    finally:
        con.close()
    print(f"classification={summary['classification']}")
    print(f"summary={config.out_dir / (config.run_id + '_summary.json')}")
    print(f"report={config.out_dir / (config.run_id + '_report.md')}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run artifact test**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py::test_run_diagnostic_writes_summary_and_report
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/diagnostics/live_threshold.py scripts/diagnose_live_thresholds.py tests/test_live_threshold_diagnostics.py
git commit -m "feat: write live threshold diagnostic artifacts"
```

---

### Task 6: Add Full Verification And Usage Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-05-08-live-threshold-diagnostics-design.md`
- Modify: `tests/test_live_threshold_diagnostics.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py
```

Expected: PASS.

- [ ] **Step 2: Run related diagnostic tests**

Run:

```bash
uv run pytest -q tests/test_diagnose_live_replay.py tests/test_live_threshold_diagnostics.py
```

Expected: PASS.

- [ ] **Step 3: Run a syntax check for the CLI**

Run:

```bash
uv run python scripts/diagnose_live_thresholds.py --help
```

Expected: exits 0 and prints arguments including `--db`, `--symbol`, `--run-id`, `--start-ts`, and `--end-ts`.

- [ ] **Step 4: Add usage example to the design spec**

Append this section to `docs/superpowers/specs/2026-05-08-live-threshold-diagnostics-design.md`:

````markdown

## Usage

Example local run:

```bash
uv run python scripts/diagnose_live_thresholds.py \
  --db data/live_state.db \
  --symbol EURUSD \
  --run-id eurusd_20260508 \
  --start-ts 2026-05-01T00:00:00Z \
  --end-ts 2026-05-08T23:59:59Z \
  --lookback-days 20 \
  --execution-quantile 0.9 \
  --min-history 300 \
  --out-dir data/analysis/live_threshold_diagnostics
```

The script writes a Markdown report and CSV/JSON artifacts under the output directory. The classification is evidence-only and does not change production Rolling Threshold behavior.
````

- [ ] **Step 5: Run Markdown and test verification**

Run:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py
uv run python scripts/diagnose_live_thresholds.py --help
```

Expected: both commands pass.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-05-08-live-threshold-diagnostics-design.md tests/test_live_threshold_diagnostics.py
git commit -m "docs: document live threshold diagnostics usage"
```

---

## Final Verification

- [ ] Run all focused tests:

```bash
uv run pytest -q tests/test_live_threshold_diagnostics.py tests/test_diagnose_live_replay.py tests/test_duckdb_state.py
```

Expected: PASS.

- [ ] Run the CLI help:

```bash
uv run python scripts/diagnose_live_thresholds.py --help
```

Expected: PASS.

- [ ] Inspect git status:

```bash
git status --short
```

Expected: only intentional tracked changes or clean after commits. Existing unrelated graphify outputs may remain untracked in the root checkout and must not be reverted by this work.

---

## Implementation Notes

- Keep the diagnostic local-only. Do not browse or pull external market data.
- Do not change `src/behemoth/api/server.py`, `src/behemoth/runtime/state.py`, or Java runtime behavior unless a separate approved implementation plan explicitly requires it.
- If Feature Set parity fails in real data, the diagnostic must stop before interpreting smoothing alternatives as actionable.
- If DuckDB runtime tables are missing, return `INCONCLUSIVE` with evidence completeness set to false rather than raising an unhandled exception.
