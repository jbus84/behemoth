# JForex Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the JForex governance pipeline (Stages 12–14) to production-ready quality: close all identified certification gaps, ensure every critical check is automated and regression-protected, and produce an all-green Stage 14 snapshot for all 6 symbols.

**Architecture:** The pipeline flows Stage 12 (API parity) → Stage 13 (Dukascopy TestClient) → Local surrogate cert (pre-Stage 14 Java harness) → Stage 14 (real Dukascopy JForex tester). Stage 14 is the hard production gate. The local surrogate cert uses parquet ticks + the Python API server + the Java strategy core; the real tester cert uses Dukascopy's JForex tester with live tick data. Both must be green before deployment.

**Tech Stack:** Python 3.12 (pytest, DuckDB, pandas), Java 21 (JUnit 5, AssertJ, DuckDB JDBC), Gradle (Kotlin DSL), Make targets

---

## Production Readiness Assessment

### Current State (2026-03-19)

| Check | Status | Notes |
|---|---|---|
| Stage 12 API parity (all 6 symbols) | ✅ Green | `stage13_dukascopy_testclient_summary.csv` |
| Stage 13 Dukascopy TestClient | ✅ Green | Real Dukascopy TestClient parity |
| Local surrogate cert (all 6 symbols) | ✅ Green | `local_jforex_surrogate_summary.csv`, all checks including outcome parity |
| Stage 14 (GBPUSD) | ✅ Green | Real JForex tester artifacts present |
| Stage 14 (EURUSD, USDJPY, USDCHF, AUDUSD, USDCAD) | ❌ Red | `missing_inputs=4` each — real tester artifacts missing |
| Signal coverage threshold | ⚠️ Lenient | Default 0.8 (80%); spotlight ticks guarantee exact hits, must be 1.0 |
| JVM UTC timezone regression test | ❌ Missing | BST/UTC JDBC bug fixed this session; no protection against regression |
| Outcome parity in Stage 14 | ❌ Missing | `jforex_outcome_parity_pass` not a Stage 14 check |
| Local surrogate cert feeds Stage 14 | ❌ Missing | `local_jforex_surrogate_pass` not a Stage 14 prerequisite |
| Staleness validation in Stage 14 | ❌ Missing | No check that input artifacts are fresh |
| OCO blocking documented | ⚠️ Unclear | `order_coverage_pass=False` for all symbols with no interpretation |

### Identified Gaps (Prioritised)

**P0 — Must fix before production:**
1. Stage 14 red for 5/6 symbols (real tester not run)
2. `jforex_outcome_parity_pass` not in Stage 14 hard gate
3. `local_jforex_surrogate_pass` not a Stage 14 prerequisite
4. JVM UTC timezone regression test missing
5. `runJForexTester` (Stage 14 real tester) missing `-Duser.timezone=UTC` in JVM args

**P1 — Fix immediately, high risk:**
5. Signal coverage threshold at 80% — must be 1.0 for spotlight cert

**P2 — Fix before go-live:**
6. Staleness validation missing from Stage 14
7. OCO blocking expected behavior not documented in cert output

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/jforex/src/test/java/com/behemoth/jforex/local/ParquetTickLoaderTimezoneTest.java` | **CREATE** | JVM timezone regression: verify `getTimestamp().toInstant()` is UTC-invariant |
| `src/jforex/build.gradle.kts` | **MODIFY** | Add `-Duser.timezone=UTC` to `runJForexTester` JVM args (same fix as `runLocalJForexTester`) |
| `Makefile` | **MODIFY** | Raise default `SIGNAL_COVERAGE_THRESHOLD` from 0.8 → 1.0 in both spotlight and outcome-parity targets |
| `scripts/validate_stage14_jforex_runtime_certification.py` | **MODIFY** | Add `jforex_outcome_parity_pass` (6th check) + `local_jforex_surrogate_pass` (7th check) + staleness validation + OCO documentation in interpretation block |
| `tests/test_validate_stage14_jforex_runtime_certification.py` | **MODIFY** | Add tests for new checks and staleness logic |
| `scripts/reconcile_jforex_outcomes.py` | **MODIFY** | Add docstring explanation of `order_coverage_ratio` OCO-blocking expected behavior |
| `Makefile` | **MODIFY** | Add `--jforex-outcome-summary-glob` and `--local-surrogate-summary-glob` to `stage14-jforex-cert` target |

---

### Task 1: JVM UTC Timezone Regression Test + Fix `runJForexTester`

**Context:** In July 2025 the system timezone is `Europe/London` (BST = UTC+1). `ParquetTickLoader.collectTicks()` calls `rs.getTimestamp("timestamp").toInstant()`. DuckDB JDBC interprets naive `TIMESTAMP` columns using the JVM's local timezone, shifting all timestamps by -1h when converting to `Instant`. This caused 0% signal coverage for USDCAD (and could silently affect any symbol). Fixed by adding `-Duser.timezone=UTC` to `runLocalJForexTester` JVM args. **`runJForexTester` (the Stage 14 real tester) is also missing this flag** — it must be patched before running Stage 14.

Relevant API facts (from reading the source):
- `ParquetTickLoader` has one public instance method: `load(LocalJForexHarnessConfig config, String symbol)` returning `ParquetTickLoader.TickWindow`
- `TickWindow` is a nested record: `record TickWindow(List<RuntimeTick> warmup, List<RuntimeTick> stream)`
- `RuntimeTick` is `com.behemoth.jforex.core.RuntimeTick` (record with `symbol`, `timestamp`, `bid`, `ask`)
- `parquetFiles()` resolves `config.tickRoot().resolve(normalizeSymbol(symbol))/` looking for `.parquet` files
- The test must create a subdirectory `{tempDir}/EURUSD/` containing a `.parquet` file

**Files:**
- Create: `src/jforex/src/test/java/com/behemoth/jforex/local/ParquetTickLoaderTimezoneTest.java`
- Modify: `src/jforex/build.gradle.kts` (add `-Duser.timezone=UTC` to `runJForexTester`)

- [ ] **Step 1: Write the failing test**

```java
package com.behemoth.jforex.local;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.core.RuntimeTick;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.time.Instant;
import java.util.List;
import java.util.TimeZone;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ParquetTickLoaderTimezoneTest {
    @TempDir
    Path tempDir;

    @Test
    void timestampReadAsUtcRegardlessOfJvmTimezone() throws Exception {
        // Write a parquet file with a known UTC timestamp as a naive TIMESTAMP column.
        // The naive TIMESTAMP value "2025-07-07 03:16:16.599" represents 03:16:16 UTC.
        // When read via getTimestamp("timestamp").toInstant() with JVM=Europe/London (BST),
        // the pre-fix result was 02:16:16 UTC (1h behind), causing gate mismatches.
        // With -Duser.timezone=UTC the Instant must exactly match the stored value.
        Instant expectedInstant = Instant.parse("2025-07-07T03:16:16.599Z");

        // ParquetTickLoader.parquetFiles() expects: tickRoot / normalizedSymbol / *.parquet
        Path symbolDir = tempDir.resolve("EURUSD");
        Files.createDirectories(symbolDir);
        Path parquet = symbolDir.resolve("test_ticks.parquet");

        // Write parquet via DuckDB: naive TIMESTAMP (no TZ info stored)
        try (Connection con = DriverManager.getConnection("jdbc:duckdb:");
             Statement st = con.createStatement()) {
            st.execute(
                "COPY (SELECT TIMESTAMP '2025-07-07 03:16:16.599' AS timestamp, "
                + "1.08500 AS bid, 1.08510 AS ask) "
                + "TO '" + parquet.toAbsolutePath() + "' (FORMAT PARQUET)"
            );
        }

        // Build a minimal config: tickRoot=tempDir, window covers the tick, no warmup/lookback
        LocalJForexHarnessConfig config = new LocalJForexHarnessConfig(
            URI.create("http://127.0.0.1:8000"),
            List.of("EURUSD"),
            Instant.parse("2025-07-07T00:00:00Z"),
            Instant.parse("2025-07-08T00:00:00Z"),
            tempDir,                   // reportDir
            "timezone-test",           // runId
            false,                     // riskEnabled
            10000.0,                   // requestedVolumeUnits
            100,                       // tickBatchSize
            900L,                      // orderTtlSeconds
            60,                        // apiTimeoutSeconds
            false,                     // metricsEnabled
            "",                        // metricsHost (ignored when metricsEnabled=false)
            0,                         // metricsPort (ignored when metricsEnabled=false)
            tempDir,                   // tickRoot
            0,                         // warmupTicks
            0,                         // lookbackDays
            100,                       // phaseBarTicks
            100000.0                   // startingBalance
        );

        // Simulate a non-UTC JVM timezone to prove invariance
        TimeZone original = TimeZone.getDefault();
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("Europe/London"));
            ParquetTickLoader.TickWindow window = new ParquetTickLoader().load(config, "EURUSD");
            List<RuntimeTick> stream = window.stream();
            assertThat(stream).hasSize(1);
            // Must match the stored UTC value, not the BST-shifted interpretation
            assertThat(stream.get(0).timestamp()).isEqualTo(expectedInstant);
        } finally {
            TimeZone.setDefault(original);
        }
    }
}
```

- [ ] **Step 2: Run the test — confirm it FAILS without `-Duser.timezone=UTC`**

Temporarily remove `-Duser.timezone=UTC` from `runLocalJForexTester` (or run tests directly without the flag) to confirm the test catches the regression:

```bash
cd /Users/danielfisher/repositories/behemoth
# Run test WITHOUT UTC flag — should FAIL (timestamp off by 1h under BST)
# The TimeZone.setDefault in the test simulates this even if the JVM default is UTC
mise exec -- gradle :jforex-adapter:test --tests "com.behemoth.jforex.local.ParquetTickLoaderTimezoneTest" --rerun-tasks 2>&1 | tail -20
```

The `TimeZone.setDefault(TimeZone.getTimeZone("Europe/London"))` call in the test itself simulates the BST environment, so this test will fail if JDBC doesn't use the JVM timezone override (i.e., if the code does NOT honour `-Duser.timezone=UTC` and instead uses whatever `TimeZone.getDefault()` returns). The test is self-contained and should fail without a fix.

- [ ] **Step 3: Fix `runJForexTester` in `build.gradle.kts`**

In `src/jforex/build.gradle.kts`, update `runJForexTester` (line 49-56):

```kotlin
tasks.register<JavaExec>("runJForexTester") {
    group = "application"
    description = "Run the real Dukascopy JForex tester harness"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("com.behemoth.jforex.JForexTesterRunner")
    workingDir = rootProject.projectDir
    jvmArgs = listOf("-Djava.awt.headless=true", "-Duser.timezone=UTC")
}
```

- [ ] **Step 4: Run test to confirm it PASSES**

```bash
mise exec -- gradle :jforex-adapter:test --tests "com.behemoth.jforex.local.ParquetTickLoaderTimezoneTest" --rerun-tasks 2>&1 | tail -20
```
Expected: `BUILD SUCCESSFUL`, 1 test passed.

Note: The test itself calls `TimeZone.setDefault("Europe/London")` before loading. The fix in `ParquetTickLoader` must use an explicit UTC Calendar or override the JDBC timestamp interpretation. If the test still fails after setting the JVM flag in `build.gradle.kts` (because `TimeZone.setDefault` overrides back to BST in the test body), the actual fix needed is to use `rs.getTimestamp("timestamp", Calendar.getInstance(TimeZone.getTimeZone("UTC")))` inside `collectTicks()`. This is the correct long-term fix — it makes the JDBC call timezone-invariant regardless of JVM default.

**If the test fails after Step 3**: modify `ParquetTickLoader.collectTicks()` to use an explicit UTC calendar:
```java
private static final java.util.Calendar UTC_CAL =
    java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));

// In collectTicks():
rs.getTimestamp("timestamp", UTC_CAL).toInstant()
```

- [ ] **Step 5: Run all Java tests to confirm no regressions**

```bash
mise exec -- gradle :jforex-adapter:test --rerun-tasks 2>&1 | tail -20
```
Expected: `BUILD SUCCESSFUL`, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/jforex/src/test/java/com/behemoth/jforex/local/ParquetTickLoaderTimezoneTest.java \
        src/jforex/build.gradle.kts
git commit -m "fix: add -Duser.timezone=UTC to runJForexTester and add JDBC timezone regression test"
```

---

### Task 2: Raise Signal Coverage Threshold to 1.0

**Context:** `local-jforex-parity-spotlight` and `jforex-outcome-parity` both default `SIGNAL_COVERAGE_THRESHOLD` to 0.8 (80%). Spotlight ticks are generated as compact windows around locked prediction events — by construction, every locked event should appear in the tick stream. 80% would silently pass a run where 1 in 5 signals are missed. The correct threshold is 1.0 for this harness.

**Files:**
- Modify: `Makefile` (lines 145 and 172)

- [ ] **Step 1: Read the current Makefile defaults**

Confirm lines 145 and 172 in `Makefile` show `$(or $(SIGNAL_COVERAGE_THRESHOLD),0.8)`.

- [ ] **Step 2: Update both defaults**

In `Makefile` line 145 (`local-jforex-parity-spotlight`):
```makefile
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),1.0) \
```

In `Makefile` line 172 (`jforex-outcome-parity`):
```makefile
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),1.0) \
```

The default changes from `0.8` to `1.0` in both places. The `$(or ...)` guard preserves the ability to override from the command line.

- [ ] **Step 3: Run `make jforex-outcome-parity` to confirm all 6 symbols still pass at 1.0**

```bash
make jforex-outcome-parity 2>&1 | tail -20
```
Expected: `All symbols PASSED outcome parity.`

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "fix: raise signal_coverage_threshold default from 0.8 to 1.0 for spotlight cert"
```

---

### Task 3: Add Outcome Parity and Local Surrogate Checks to Stage 14

**Context:** `validate_stage14_jforex_runtime_certification.py` has 5 checks: stage13, signal, execution, lifecycle, operational. Two critical checks are missing:
1. `jforex_outcome_parity_pass` — reconciles locked Python predictions against JForex runtime events (signal coverage ≥ 1.0, zero execution failures, has trades). Produced by `reconcile_jforex_outcomes.py`.
2. `local_jforex_surrogate_pass` — the Java core must pass the parquet harness before the real broker test is trusted. Produced by `validate_local_jforex_surrogate.py` → `local_jforex_surrogate_summary.csv`.

**Important naming facts:**
- `reconcile_jforex_outcomes.py` writes per-symbol files as `{symbol}_local_jforex_outcome_parity_summary.csv` (always has `_local_jforex_` in the name regardless of tick source) AND writes an aggregate `jforex_outcome_parity_summary.csv` (no `_local_jforex_` prefix) via `--out-csv`.
- For Stage 14, use the **aggregate** `jforex_outcome_parity_summary.csv` as the glob. This file has `overall_pass` column for all 6 symbols in a single CSV. The `InputSource.candidate_columns` fallback `"overall_pass"` will correctly resolve it.
- Do NOT use the per-symbol `*_local_jforex_outcome_parity_summary.csv` glob — these files would be rejected by Stage 14's existing `excluded_path_substrings=("_local_jforex_",)` filters on other checks, and more importantly the per-symbol outcome files contain `_local_jforex_` in the path, signalling they came from the local harness rather than a real tester run.
- `local_jforex_surrogate_summary.csv` does not contain `_local_jforex_` in its filename so it is not affected by the exclusion filter.

**Files:**
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`
- Modify: `Makefile` (add 2 new glob args to `stage14-jforex-cert`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validate_stage14_jforex_runtime_certification.py`:

```python
def test_build_stage14_artifacts_includes_outcome_parity_check(tmp_path: Path) -> None:
    """Stage 14 must include jforex_outcome_parity_pass as a check."""
    _write_csv(tmp_path / "EURUSD_stage13.csv",
               [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_signal.csv",
               [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_execution.csv",
               [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_lifecycle.csv",
               [{"symbol": "EURUSD", "oco_lifecycle_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_ops.csv",
               [{"symbol": "EURUSD", "operational_ready_pass": True}])
    # outcome parity missing — should cause stage14 to fail
    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) >= 1
    outcome_check = checks[checks["metric_name"] == "jforex_outcome_parity_pass"]
    assert len(outcome_check) == 1
    assert outcome_check.iloc[0]["status"] == "fail"


def test_build_stage14_artifacts_includes_local_surrogate_check(tmp_path: Path) -> None:
    """Stage 14 must include local_jforex_surrogate_pass as a prerequisite check."""
    _write_csv(tmp_path / "EURUSD_stage13.csv",
               [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_signal.csv",
               [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_execution.csv",
               [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_lifecycle.csv",
               [{"symbol": "EURUSD", "oco_lifecycle_pass": True}])
    _write_csv(tmp_path / "EURUSD_jforex_ops.csv",
               [{"symbol": "EURUSD", "operational_ready_pass": True}])
    _write_csv(tmp_path / "EURUSD_outcome.csv",
               [{"symbol": "EURUSD", "jforex_outcome_parity_pass": True}])
    # local surrogate missing — should cause stage14 to fail
    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "fail"


def test_build_stage14_artifacts_green_with_all_seven_checks(tmp_path: Path) -> None:
    """Stage 14 is green only when all 7 checks pass (5 original + outcome + surrogate)."""
    for name, col, val in [
        ("stage13", "stage13_dukascopy_testclient_pass", True),
        ("jforex_signal", "jforex_signal_parity_pass", True),
        ("jforex_execution", "jforex_execution_parity_pass", True),
        ("jforex_lifecycle", "oco_lifecycle_pass", True),
        ("jforex_ops", "operational_ready_pass", True),
        ("outcome", "jforex_outcome_parity_pass", True),
    ]:
        _write_csv(tmp_path / f"EURUSD_{name}.csv", [{"symbol": "EURUSD", col: val}])
    # local surrogate summary uses overall key "local_jforex_surrogate_pass"
    _write_csv(tmp_path / "local_surrogate.csv",
               [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}])

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 7
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_validate_stage14_jforex_runtime_certification.py -k "outcome_parity or local_surrogate or seven_checks" -v 2>&1 | tail -20
```
Expected: 3 tests FAIL (TypeError or missing columns).

- [ ] **Step 3: Update `build_stage14_artifacts` signature and body**

In `scripts/validate_stage14_jforex_runtime_certification.py`:

Add two new parameters to `build_stage14_artifacts`:
```python
jforex_outcome_summary_glob: str = "",
local_surrogate_summary_glob: str = "",
```

Add two new `InputSource` entries to the `sources` list (after existing 5):
```python
InputSource(
    check_id="jforex_outcome_parity_pass",
    summary_glob=jforex_outcome_summary_glob,
    candidate_columns=("jforex_outcome_parity_pass", "overall_pass"),
),
InputSource(
    check_id="local_jforex_surrogate_pass",
    summary_glob=local_surrogate_summary_glob,
    candidate_columns=("local_jforex_surrogate_pass", "verdict"),
),
```

Note: `local_jforex_surrogate_pass` uses `verdict` as a fallback column (value `"green"` maps to True via `_pick_bool`). No `excluded_path_substrings` needed — the surrogate summary CSV does not have `_local_jforex_` in its filename.

Update the interpretation block in `report_lines` to add:
```
- jforex_outcome_parity_pass: reconciles JForex runtime signal counts against locked Python predictions (signal_coverage_ratio must be 1.0, zero execution failures, trades present).
- local_jforex_surrogate_pass: the shared Java strategy core must pass all checks in the parquet-driven local surrogate harness before the real broker test is trusted.
- order_coverage_ratio is expected to be low (<0.2): OCO mechanics block new orders while an existing position is live. This metric is informational; signal_coverage_pass is the gate.
```

Update `main()` to add two new `argparse` arguments:
```python
parser.add_argument("--jforex-outcome-summary-glob", default="")
parser.add_argument("--local-surrogate-summary-glob", default="")
```
And pass them to `build_stage14_artifacts`.

- [ ] **Step 4: Update existing tests to pass new required args**

All existing calls to `build_stage14_artifacts` in the test file need the two new keyword arguments added (both defaulting to `""`). The `checks` count in `test_build_stage14_artifacts_marks_green_when_all_checks_pass` must be updated from `5` to `7` (when both new globs are provided and pass), but since those existing tests pass `""` for the new globs, they now have 2 additional missing inputs. Update:
- `test_build_stage14_artifacts_marks_green_when_all_checks_pass`: Add new fixture CSVs for outcome + surrogate or pass `""` and adjust `missing_inputs` expectation
- `test_build_stage14_artifacts_fails_when_jforex_inputs_missing`: `missing_inputs` was 4, now 6 (adds outcome + surrogate)
- `test_build_stage14_artifacts_keeps_requested_symbol_scope`: `checks` count was 5, now 7

The cleanest approach: in all existing tests that don't specify the new globs, pass `jforex_outcome_summary_glob=""` and `local_surrogate_summary_glob=""` explicitly, then adjust `missing_inputs` and `len(checks)` assertions accordingly.

- [ ] **Step 5: Update `stage14-jforex-cert` Makefile target**

Add two new args to the `stage14-jforex-cert` target in `Makefile`:
```makefile
		--jforex-outcome-summary-glob '$(or $(JFOREX_OUTCOME_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_outcome_parity_summary.csv)' \
		--local-surrogate-summary-glob '$(or $(LOCAL_SURROGATE_SUMMARY_GLOB),data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv)' \
```

Important: The outcome glob is `*_jforex_outcome_parity_summary.csv` (NOT `*_local_jforex_outcome_parity_summary.csv`). For real tester runs, `reconcile_jforex_outcomes.py` writes `{symbol}_jforex_outcome_parity_summary.csv` (without `_local_jforex_` in the name). This is the same file pattern used by `jforex-outcome-parity`.

Wait — actually check this. Looking at `reconcile_jforex_outcomes.py:218`:
```python
path = out_dir / f"{symbol}_local_jforex_outcome_parity_summary.csv"
```
The per-symbol file is `{symbol}_local_jforex_outcome_parity_summary.csv`. The aggregate is `jforex_outcome_parity_summary.csv`. For Stage 14 we want the per-symbol files for each real tester run. The real tester runtime events dir will be `data/analysis/backtest_reconcile/` (same dir as local). So the glob `*_jforex_outcome_parity_summary.csv` would match both `*_local_jforex_*` and real tester `*_jforex_*`. We need to ensure the glob only picks up real tester outcomes.

Since `reconcile_jforex_outcomes.py` writes the same `{symbol}_local_jforex_outcome_parity_summary.csv` regardless of whether ticks came from the local harness or the real tester (it reads the runtime events CSV, which is named differently), the Stage 14 glob should use the aggregate outcome CSV `jforex_outcome_parity_summary.csv` (the `--out-csv` path), NOT the per-symbol local files.

The aggregate file has one row per symbol. Use:
```
data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv
```

This file has all 6 symbols and uses `overall_pass` as the column. The `InputSource` for Stage 14 uses `candidate_columns=("jforex_outcome_parity_pass", "overall_pass")`. Since `reconcile_jforex_outcomes.py` writes `overall_pass=True/False` in the aggregate CSV, `_pick_bool` will correctly resolve this.

Update the Makefile default for `--jforex-outcome-summary-glob` to:
```makefile
data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv
```

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest tests/test_validate_stage14_jforex_runtime_certification.py -v 2>&1 | tail -30
```
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/validate_stage14_jforex_runtime_certification.py \
        tests/test_validate_stage14_jforex_runtime_certification.py \
        Makefile
git commit -m "feat: add outcome_parity and local_surrogate_pass checks to Stage 14 certification gate"
```

---

### Task 4: Add Staleness Validation to Stage 14

**Context:** Stage 14 checks are built from input CSVs. If those CSVs were generated 3 weeks ago (stale run) the cert is meaningless. A `--max-artifact-age-days` arg (default 7) should fail any symbol where an input artifact's `evaluated_at_utc` is older than the threshold. This prevents silently certifying against stale data after a model change.

**Files:**
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`
- Modify: `tests/test_validate_stage14_jforex_runtime_certification.py`

- [ ] **Step 1: Write failing tests for staleness**

Add to `tests/test_validate_stage14_jforex_runtime_certification.py`:

```python
from datetime import datetime, timedelta, timezone


def _utc_str(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_build_stage14_artifacts_fails_when_input_artifact_is_stale(tmp_path: Path) -> None:
    """A Stage 14 input CSV with evaluated_at_utc older than max_artifact_age_days must fail."""
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True,
          "evaluated_at_utc": stale_ts}],
    )
    # all other inputs: fresh
    for name, col in [
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
    ]:
        _write_csv(tmp_path / f"EURUSD_{name}.csv",
                   [{"symbol": "EURUSD", col: True, "evaluated_at_utc": _utc_str()}])
    _write_csv(tmp_path / "EURUSD_lifecycle.csv",
               [{"symbol": "EURUSD", "oco_lifecycle_pass": True, "evaluated_at_utc": _utc_str()}])
    _write_csv(tmp_path / "EURUSD_ops.csv",
               [{"symbol": "EURUSD", "operational_ready_pass": True, "evaluated_at_utc": _utc_str()}])

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        max_artifact_age_days=7,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    stale_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"]
    assert stale_check.iloc[0]["status"] == "fail"
    assert "stale" in stale_check.iloc[0]["details"].lower()


def test_build_stage14_artifacts_passes_when_all_fresh(tmp_path: Path) -> None:
    """Staleness check must not fire when all inputs are recent."""
    fresh_ts = _utc_str()
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("lifecycle", "oco_lifecycle_pass"),
        ("ops", "operational_ready_pass"),
    ]:
        _write_csv(tmp_path / f"EURUSD_{name}.csv",
                   [{"symbol": "EURUSD", col: True, "evaluated_at_utc": fresh_ts}])

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        max_artifact_age_days=7,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    # missing_inputs=2 for outcome+surrogate (both empty globs), so cert still fails overall
    # but the stage13 check must be "pass" (not stale)
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"]
    assert stage13_check.iloc[0]["status"] == "pass"
    assert stage13_check.iloc[0]["details"] == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_validate_stage14_jforex_runtime_certification.py -k "stale" -v 2>&1 | tail -15
```
Expected: FAIL (TypeError — `max_artifact_age_days` not accepted).

- [ ] **Step 3: Implement staleness check**

In `scripts/validate_stage14_jforex_runtime_certification.py`:

1. Add `max_artifact_age_days: int = 7` parameter to `build_stage14_artifacts`.

2. Add a helper to `_load_summary_rows` to also capture `evaluated_at_utc` from the row:
   ```python
   rows.append({
       "symbol": symbol,
       "check_id": source.check_id,
       "pass": _pick_bool(row, source.candidate_columns),
       "source_path": str(path),
       "evaluated_at_utc": str(row.get("evaluated_at_utc") or ""),
   })
   ```

3. In the symbol-level loop, after resolving `value`, add staleness logic:
   ```python
   if value is True and max_artifact_age_days > 0:
       eval_ts_str = "" if match.empty else str(match.iloc[-1].get("evaluated_at_utc") or "")
       if eval_ts_str:
           try:
               eval_ts = datetime.fromisoformat(eval_ts_str.replace("Z", "+00:00"))
               age_days = (datetime.now(timezone.utc) - eval_ts).days
               if age_days > max_artifact_age_days:
                   value = False
                   details = f"stale: artifact is {age_days}d old (max {max_artifact_age_days}d)"
           except ValueError:
               pass
   ```

4. Add `max_artifact_age_days` to `main()` via `argparse`:
   ```python
   parser.add_argument("--max-artifact-age-days", type=int, default=7)
   ```
   Pass to `build_stage14_artifacts`.

5. Add to `stage14-jforex-cert` Makefile target:
   ```makefile
   		--max-artifact-age-days $(or $(MAX_ARTIFACT_AGE_DAYS),7) \
   ```

- [ ] **Step 4: Run all Stage 14 tests**

```bash
uv run pytest tests/test_validate_stage14_jforex_runtime_certification.py -v 2>&1 | tail -30
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_stage14_jforex_runtime_certification.py \
        tests/test_validate_stage14_jforex_runtime_certification.py \
        Makefile
git commit -m "feat: add staleness validation to Stage 14 — fail if input artifacts are >7 days old"
```

---

### Task 5: Document OCO Blocking in `reconcile_jforex_outcomes.py`

**Context:** `order_coverage_ratio` is ~1.7–13% across all symbols. This is expected: the OCO strategy enters one position and blocks new orders until that position closes. In a 2-day evaluation window (July 7–9), only a few unique prediction events actually result in new order submissions. The `order_coverage_pass` column is `False` for all symbols but this is correctly excluded from `overall_pass`. Without documentation, a reviewer could incorrectly flag this as a bug.

**Files:**
- Modify: `scripts/reconcile_jforex_outcomes.py` (docstring of `compare_outcomes`)

- [ ] **Step 1: Update `compare_outcomes` docstring**

In `reconcile_jforex_outcomes.py`, update the docstring of `compare_outcomes` to add:

```python
    Notes:
        order_coverage_ratio is expected to be materially below 1.0 in live/tester runs.
        The OCO strategy allows only one open position at a time.  Once an order group is
        submitted, subsequent predict cycles that select candidates are counted in
        jforex_selected_total (signal_coverage) but do NOT submit new orders while the
        position is live.  order_coverage_pass is therefore informational and is intentionally
        excluded from overall_pass.  signal_coverage_pass is the actionable gate.
```

- [ ] **Step 2: Run tests to confirm no regressions**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -v 2>&1 | tail -10
```
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add scripts/reconcile_jforex_outcomes.py
git commit -m "docs: explain OCO-blocking as expected cause of low order_coverage_ratio"
```

---

### Task 6: Run Real JForex Tester for Remaining 5 Symbols and Produce All-Green Stage 14 Snapshot

**Context:** Stage 14 is currently red for EURUSD, USDJPY, USDCHF, AUDUSD, USDCAD because real Dukascopy JForex tester artifacts don't exist. Only GBPUSD has been tested via `jforex-dukascopy-matrix`. The `jforex-dukascopy-matrix` target runs the real JForex strategy but does NOT call `reconcile_jforex_outcomes.py`. We need to: (1) run the real tester, (2) run outcome reconciliation, (3) regenerate Stage 14 cert.

This task requires the real Dukascopy JForex tester environment (live credentials, `JFOREX_LOGIN`, `JFOREX_PASSWORD` etc. in environment). It is an execution task, not a code change. Steps are manual Makefile invocations.

**Files:**
- No code changes. Executes existing Makefile targets.
- Outputs: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`, `docs/strategy_bible/generated/stage_14_snapshot.md`

- [ ] **Step 1: Verify Dukascopy credentials are available**

```bash
echo "JFOREX_LOGIN=${JFOREX_LOGIN:-NOT_SET}"
echo "JFOREX_PASSWORD=${JFOREX_PASSWORD:-NOT_SET}"
```
Expected: Both set. If not, obtain credentials before proceeding.

- [ ] **Step 2: Run `jforex-outcome-parity` to confirm existing local surrogate outcomes are current**

```bash
make jforex-outcome-parity 2>&1 | tail -15
```
Expected: `All symbols PASSED outcome parity.` with `signal_coverage_ratio=1.0` for all 6 symbols. This confirms the Python side (locked predictions) is in sync before the real tester run.

- [ ] **Step 3: Run real JForex tester for all 6 symbols**

```bash
make jforex-dukascopy-matrix SYMBOLS="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD" 2>&1 | tee /tmp/jforex_matrix_run.log
```

This runs the real Dukascopy JForex tester sequentially for all symbols. Expected runtime: 30–90 minutes depending on tick volume. Check `/tmp/jforex_matrix_run.log` for errors.

After completion, verify the real tester artifacts exist:
```bash
ls data/analysis/backtest_reconcile/EURUSD_jforex_signal_parity_summary.csv
ls data/analysis/backtest_reconcile/USDJPY_jforex_signal_parity_summary.csv
ls data/analysis/backtest_reconcile/USDCHF_jforex_signal_parity_summary.csv
ls data/analysis/backtest_reconcile/AUDUSD_jforex_signal_parity_summary.csv
ls data/analysis/backtest_reconcile/USDCAD_jforex_signal_parity_summary.csv
```

- [ ] **Step 4: Run `jforex-outcome-parity` against real tester runtime events**

The real tester writes `{SYMBOL}_jforex_runtime_events.csv` (no `_local_` prefix). Run:

```bash
make jforex-outcome-parity RECONCILE_DIR=data/analysis/backtest_reconcile 2>&1 | tail -20
```

Verify `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv` shows `overall_pass=True` for all 6 symbols.

- [ ] **Step 5: Run `make local-jforex-cert` to confirm local surrogate cert is still green**

```bash
make local-jforex-cert 2>&1 | tail -10
```
Expected: all 6 symbols green (`local_jforex_surrogate_pass=True`).

- [ ] **Step 6: Run `make stage14-jforex-cert` to produce all-green Stage 14 snapshot**

```bash
make stage14-jforex-cert 2>&1 | tail -20
```

Then verify:
```bash
python -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv')
print(df[['symbol','verdict','missing_inputs','stage14_jforex_cert_pass']])
all_green = all(df['verdict'] == 'green')
print('ALL GREEN:', all_green)
"
```
Expected: `verdict=green`, `missing_inputs=0`, `stage14_jforex_cert_pass=True` for all 6 symbols.

- [ ] **Step 7: Commit the generated certification artifacts**

```bash
git add \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv \
  data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/*_jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv \
  data/analysis/backtest_reconcile/*_jforex_execution_parity_summary.csv \
  data/analysis/backtest_reconcile/*_jforex_oco_lifecycle_summary.csv \
  data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv \
  docs/strategy_bible/generated/stage_14_snapshot.md \
  docs/analysis/stage14_jforex_runtime_certification_report.md
git commit -m "cert: Stage 14 all-green snapshot for all 6 symbols — real JForex tester certified"
```

---

## Completion Checklist

Before declaring production-ready:

- [ ] `make test-java` passes (includes ParquetTickLoader timezone regression test)
- [ ] `make local-jforex-parity-spotlight` passes with `signal_coverage_threshold=1.0` for all 6 symbols
- [ ] `make jforex-outcome-parity` passes with `signal_coverage_ratio=1.0` for all 6 symbols
- [ ] `make local-jforex-cert` passes (all 6 symbols green)
- [ ] `make stage14-jforex-cert` produces all-green for all 6 symbols (7 checks each)
- [ ] Stage 14 snapshot committed at `docs/strategy_bible/generated/stage_14_snapshot.md`
- [ ] No tests failing: `uv run pytest tests/ -x -q`

## Post-Certification Notes for Live Deployment

1. **Timezone**: `runJForexTester` now has `-Duser.timezone=UTC` (fixed in Task 1). Before going live, also verify `runJForexLive` in `build.gradle.kts` has this flag — live trading also reads parquet files via JDBC.
2. **Lock dir**: Ensure `LOCK_DIR` points to the current model month's locked predictions before re-running any certification.
3. **Staleness**: Stage 14 artifacts older than 7 days will fail the cert on re-run. Re-certify at each model month rotation.
4. **Order coverage**: `order_coverage_pass=False` is expected and documented. Do not treat this as a blocker.
