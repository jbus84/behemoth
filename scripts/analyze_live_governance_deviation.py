#!/usr/bin/env python3
"""Run live governance deviation diagnostics from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.diagnostics.live_governance_deviation import (  # noqa: E402
    ACTIVE_SYMBOLS,
    DeviationConfig,
    run_analysis,
)


def _parse_symbols(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return ACTIVE_SYMBOLS

    symbols: list[str] = []
    seen: set[str] = set()
    for token in raw.split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return tuple(symbols) if symbols else ACTIVE_SYMBOLS


def _parse_ts(raw: str | None) -> pd.Timestamp | None:
    if raw is None or not raw.strip():
        return None
    try:
        ts = pd.Timestamp(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            f"invalid timestamp {raw!r}: {exc}"
        ) from exc
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run live governance deviation diagnostics."
    )
    parser.add_argument(
        "--runtime-db",
        type=Path,
        default=Path("data/analysis/backtest_reconcile/runtime/live_state.db"),
    )
    parser.add_argument(
        "--tick-root",
        type=Path,
        default=Path("/Users/danielfisher/Desktop/dukascopy_ticks"),
    )
    parser.add_argument("--symbols", default=",".join(ACTIVE_SYMBOLS))
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--min-bars", type=int, default=100)
    parser.add_argument("--run-id", default="jforex_live")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/analysis/live_governance_deviation"),
    )
    parser.add_argument("--start-ts", type=_parse_ts, default=None)
    parser.add_argument("--end-ts", type=_parse_ts, default=None)
    parser.add_argument(
        "--governance-dir",
        type=Path,
        default=Path("configs/research/governance/oco"),
    )
    parser.add_argument("--models-dir", type=Path, default=Path("models/oco"))
    parser.add_argument("--api", default="")
    parser.add_argument("--copy-report-to-docs", action="store_true")
    args = parser.parse_args(argv)
    if (args.start_ts is None) != (args.end_ts is None):
        parser.error("--start-ts and --end-ts must be supplied together")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = DeviationConfig(
        runtime_db=args.runtime_db,
        tick_root=args.tick_root,
        symbols=_parse_symbols(args.symbols),
        lookback_days=args.lookback_days,
        min_bars=args.min_bars,
        run_id=args.run_id,
        out_dir=args.out_dir,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
        governance_dir=args.governance_dir,
        models_dir=args.models_dir,
        api=args.api or None,
        copy_report_to_docs=args.copy_report_to_docs,
    )
    paths = run_analysis(cfg)
    print(f"run_dir={paths['run_dir']}")
    print(f"manifest={paths['manifest_path']}")
    print(f"report={paths['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
