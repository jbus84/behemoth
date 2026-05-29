"""Parallel orchestrator for `make retrain-all`.

Spawns one subprocess per symbol via a ThreadPoolExecutor (each task
shells out to onboard_symbol.py, so I/O-bound waits dominate and no
GIL contention occurs) and aggregates outcomes in REBUILD_SYMBOLS
order. Replaces the Makefile's serial `for sym in $(REBUILD_SYMBOLS)`
loop while keeping the per-symbol onboard_symbol.py invocation
unchanged.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# Put the repo root on sys.path so `from scripts.classify_retrain_outcome
# import ...` below resolves when this file is run directly
# (`uv run python scripts/retrain_all_parallel.py`), not only when
# imported as a package under pytest. Same bootstrap as
# scripts/run_tick_opportunity_mining.py (PR #194).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.classify_retrain_outcome import classify_outcome  # noqa: E402

DEFAULT_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
)


@dataclass(frozen=True)
class WorkerResult:
    symbol: str
    exit_code: int
    log_path: Path
    elapsed_s: float


@dataclass(frozen=True)
class SymbolSummary:
    symbol: str
    outcome: str       # "DEPLOY" | "NO_TRADE" | "FAILED"
    exit_code: int
    log_path: Path
    elapsed_s: float


def run_worker(
    symbol: str,
    *,
    eval_end_month: str | None,
    log_dir: Path,
    stream_to_stdout: bool = False,
) -> WorkerResult:
    """Invoke onboard_symbol.py for one symbol as a subprocess.

    Output routing:
    - stream_to_stdout=True (single-worker mode): subprocess inherits
      the parent's stdout/stderr so the user sees mining progress in
      real time. log_path still records the destination — written as
      `<terminal>` — for the summary block.
    - stream_to_stdout=False (multi-worker mode): stdout+stderr go to
      `{log_dir}/{symbol}.log` so concurrent workers don't interleave
      on the terminal. Tail those logs from another shell to follow.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{symbol}.log"
    cmd = [
        "uv", "run", "python",
        "scripts/onboard_symbol.py",
        "--symbol", symbol,
        "--skip-data",
        "--skip-docs",
        "--skip-registration",
        "--model-export-dir", "models/oco",
    ]
    if eval_end_month:
        cmd += ["--eval-end-month", eval_end_month]
    t0 = time.perf_counter()
    if stream_to_stdout:
        # Inherit parent fds → child writes directly to terminal.
        print(f"  [start {symbol} streaming to terminal]", flush=True)
        proc = subprocess.run(cmd, check=False)
        print(f"  [end   {symbol} streaming]", flush=True)
    else:
        with log_path.open("w") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    return WorkerResult(
        symbol=symbol,
        exit_code=int(proc.returncode),
        log_path=log_path,
        elapsed_s=time.perf_counter() - t0,
    )


def collect_outcomes(
    results: Iterable[WorkerResult],
    *,
    symbols_order: list[str],
    analysis_dir: Path,
) -> list[SymbolSummary]:
    """Map WorkerResult → SymbolSummary in REBUILD_SYMBOLS order using
    classify_outcome on each symbol's reduced_state_schedule.csv."""
    by_sym: dict[str, WorkerResult] = {r.symbol: r for r in results}
    out: list[SymbolSummary] = []
    for sym in symbols_order:
        r = by_sym.get(sym)
        if r is None:
            out.append(SymbolSummary(
                symbol=sym, outcome="FAILED", exit_code=-1,
                log_path=Path(os.devnull), elapsed_s=0.0,
            ))
            continue
        sched = analysis_dir / "reduced_core_rolling" / f"{sym}_oco_first_touch_reduced_state_schedule.csv"
        outcome = classify_outcome(exit_code=r.exit_code, schedule_csv=sched)
        out.append(SymbolSummary(
            symbol=sym, outcome=outcome, exit_code=r.exit_code,
            log_path=r.log_path, elapsed_s=r.elapsed_s,
        ))
    return out


def run_orchestrator(
    *,
    symbols: list[str],
    max_workers: int,
    eval_end_month: str | None,
    log_dir: Path,
    analysis_dir: Path,
) -> tuple[int, list[SymbolSummary]]:
    """Run all symbols concurrently, return (exit_code, ordered_summary).
    Exit code is 1 if any symbol FAILED, else 0."""
    # Single-worker mode streams the subprocess directly to the
    # terminal so the user sees mining progress live. Multi-worker
    # mode captures per-symbol logs to disk to avoid interleave.
    stream = max_workers == 1
    if stream:
        print(
            f"=== Parallel retrain: {len(symbols)} symbols, 1 worker "
            f"(streaming subprocess output to this terminal) ===",
            flush=True,
        )
    else:
        print(
            f"=== Parallel retrain: {len(symbols)} symbols, {max_workers} "
            f"workers (per-symbol logs in {log_dir} — "
            f"`tail -f {log_dir}/EURUSD.log` etc.) ===",
            flush=True,
        )
    log_dir.mkdir(parents=True, exist_ok=True)
    results: list[WorkerResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                run_worker, sym,
                eval_end_month=eval_end_month, log_dir=log_dir,
                stream_to_stdout=stream,
            ): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except Exception as exc:
                sym = futures[fut]
                print(f"  [crash {sym}: {exc!r}]")
                r = WorkerResult(
                    symbol=sym,
                    exit_code=-1,
                    log_path=log_dir / f"{sym}.log",
                    elapsed_s=0.0,
                )
            else:
                print(f"  [done {r.symbol} exit={r.exit_code} elapsed={r.elapsed_s:.0f}s log={r.log_path}]")
            results.append(r)

    summary = collect_outcomes(results, symbols_order=symbols, analysis_dir=analysis_dir)
    print("\n══════════ Retrain summary ══════════")
    for s in summary:
        print(f"  {s.symbol}: {s.outcome} (exit={s.exit_code}, elapsed={s.elapsed_s:.0f}s)")
    print("═════════════════════════════════════")

    any_failed = any(s.outcome == "FAILED" for s in summary)
    if any_failed:
        print("❌ One or more symbols FAILED")
        return 1, summary
    return 0, summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                   help="Comma-separated symbols (default: all 6 majors)")
    p.add_argument("--max-workers", type=int, default=6,
                   help="ThreadPoolExecutor workers (default 6)")
    p.add_argument("--eval-end-month", default=None,
                   help="Passed through to onboard_symbol.py")
    p.add_argument("--log-dir", default="/tmp/retrain_logs",
                   help="Per-symbol log directory")
    p.add_argument("--analysis-dir",
                   default="data/analysis/tick_opportunity_mining",
                   help="Where reduced_core_rolling/*.csv lives (for outcome classification)")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    exit_code, _ = run_orchestrator(
        symbols=symbols,
        max_workers=int(args.max_workers),
        eval_end_month=args.eval_end_month,
        log_dir=Path(args.log_dir),
        analysis_dir=Path(args.analysis_dir),
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
