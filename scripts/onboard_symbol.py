#!/usr/bin/env python3
"""End-to-end symbol onboarding orchestrator.

Usage:
    make onboard-symbol SYMBOL=USDCAD MONTHS=201801,201802,...,202602

Runs every step from HistData tick download through to validated MkDocs build.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs" / "research" / "experiments"
BIBLE_MANIFEST = ROOT / "configs" / "research" / "docs" / "oco_bible_manifest.yaml"
MKDOCS_YML = ROOT / "mkdocs.yml"
TICK_ROOT = Path.home() / "Desktop" / "tick"
TICKBAR_DIR = ROOT / "data" / "global_tickbars"
TOM_DIR = ROOT / "data" / "analysis" / "tick_opportunity_mining"

# Scripts that have hardcoded symbol lists that we need to patch
CATALOG_SCRIPT = ROOT / "scripts" / "build_docs_catalog.py"
DRIFT_SCRIPT = ROOT / "scripts" / "build_oco_execution_drift_report.py"
THRESHOLD_SCRIPT = ROOT / "scripts" / "build_oco_threshold_sensitivity_report.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, dry_run: bool, label: str) -> None:
    """Run a subprocess, printing the command first."""
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}=== {label} ===")
    print(f"  $ {' '.join(cmd)}")
    if dry_run:
        return
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"  !! FAILED (exit {result.returncode})")
        sys.exit(result.returncode)


def _uv_run(script: str, *args: str, dry_run: bool, label: str) -> None:
    """Shorthand for `uv run python scripts/<script> ...`."""
    cmd = ["uv", "run", "python", f"scripts/{script}"] + list(args)
    _run(cmd, dry_run=dry_run, label=label)


def _months_range(start: str, end: str) -> list[str]:
    """Generate YYYYMM values from start to end inclusive."""
    sy, sm = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    months: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


# ---------------------------------------------------------------------------
# Stage 0: Data Acquisition
# ---------------------------------------------------------------------------


def stage_0_data(symbol: str, months: str, *, dry_run: bool, force: bool) -> None:
    """Download ticks from HistData and build tick bars + velocity features."""
    sym_tick_dir = TICK_ROOT / symbol
    # Check if the latest requested month already has a parquet file
    months_list = [m.strip() for m in months.split(",") if m.strip()]
    last_month = months_list[-1] if months_list else ""
    latest_parquet = sym_tick_dir / f"{symbol}_{last_month}_ticks.parquet" if last_month else None
    has_latest = latest_parquet is not None and latest_parquet.exists()
    if has_latest and not force:
        print(f"\n  skip download: {latest_parquet} already exists (use --force to re-download)")
    else:
        _uv_run(
            "download_histdata_ticks.py",
            "--symbols",
            symbol,
            "--months",
            months,
            "--tick-root",
            str(TICK_ROOT),
            dry_run=dry_run,
            label="Stage 0a: Download HistData ticks",
        )

    # Build tick bars (50, 100, 200)
    bar_path = TICKBAR_DIR / f"{symbol}_100tick.parquet"
    if bar_path.exists() and not force:
        print(f"\n  skip tick bars: {bar_path} exists (use --force)")
    else:
        _uv_run(
            "build_global_tick_bars.py",
            "--symbols",
            symbol,
            "--tick-root",
            str(TICK_ROOT),
            "--output-dir",
            str(TICKBAR_DIR),
            *(["--overwrite"] if force else []),
            dry_run=dry_run,
            label="Stage 0b: Build global tick bars",
        )

    # Build velocity features
    _uv_run(
        "build_tick_velocity_dataset.py",
        "--symbols",
        symbol,
        "--auto-build-bars",
        "--tickbar-dir",
        str(TICKBAR_DIR),
        "--tick-root",
        str(TICK_ROOT),
        *(["--overwrite"] if force else []),
        dry_run=dry_run,
        label="Stage 0c: Build velocity dataset",
    )


# ---------------------------------------------------------------------------
# Stage 1: Config Cloning
# ---------------------------------------------------------------------------


def stage_1_configs(symbol: str, *, dry_run: bool, force: bool) -> list[Path]:
    """Clone EURUSD configs, substituting the new symbol."""
    sym_lower = symbol.lower()
    templates = sorted(CONFIG_DIR.glob("eurusd*.yaml"))
    created: list[Path] = []

    for tpl in templates:
        new_name = tpl.name.replace("eurusd", sym_lower)
        new_path = CONFIG_DIR / new_name
        if new_path.exists() and not force:
            print(f"  skip config: {new_name} exists")
            created.append(new_path)
            continue

        print(f"  {'[DRY-RUN] ' if dry_run else ''}clone {tpl.name} -> {new_name}")
        if not dry_run:
            text = tpl.read_text(encoding="utf-8")
            text = text.replace("EURUSD", symbol.upper())
            text = text.replace("eurusd", sym_lower)
            # Standardise stop-limit detail path to fullcap dir
            text = re.sub(
                r"stop_limit_tickfill_\w+/",
                "stop_limit_tickfill_fullcap/",
                text,
            )
            new_path.write_text(text, encoding="utf-8")
        created.append(new_path)

    return created


# ---------------------------------------------------------------------------
# Stage 2: ML Pipeline
# ---------------------------------------------------------------------------


def stage_2_ml_pipeline(symbol: str, *, model_export_dir: str | None = None, dry_run: bool) -> None:
    """Run the 6 core ML scripts in sequence."""
    sym = symbol.lower()

    _uv_run(
        "build_tick_opportunity_ml_dataset.py",
        "--config",
        f"configs/research/experiments/{sym}_tick_opportunity_ml_dataset.yaml",
        dry_run=dry_run,
        label="Stage 2a: Build ML dataset",
    )

    _uv_run(
        "run_tick_opportunity_mining.py",
        "--config",
        f"configs/research/experiments/{sym}_tick_opportunity_mining.yaml",
        dry_run=dry_run,
        label="Stage 2b: Opportunity mining",
    )

    wfo_args_base = [
        "--config", f"configs/research/experiments/{sym}_tick_opportunity_monthly_wfo_2025.yaml"
    ]
    if model_export_dir:
        wfo_args_base += ["--model-export-dir", model_export_dir]

    _uv_run(
        "run_tick_opportunity_monthly_wfo.py",
        *wfo_args_base,
        dry_run=dry_run,
        label="Stage 2c: Base WFO",
    )

    wfo_args_oco = [
        "--config", f"configs/research/experiments/{sym}_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml"
    ]
    if model_export_dir:
        wfo_args_oco += ["--model-export-dir", model_export_dir]

    _uv_run(
        "run_tick_opportunity_monthly_wfo.py",
        *wfo_args_oco,
        dry_run=dry_run,
        label="Stage 2d: OCO Fullcap WFO",
    )

    pred_path = f"data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/{symbol.upper()}_oco_monthly_predictions.parquet"
    _uv_run(
        "analyze_oco_stop_limit_tickfill.py",
        "--symbols",
        symbol.upper(),
        "--pred-paths",
        pred_path,
        "--out-dir",
        "data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap",
        dry_run=dry_run,
        label="Stage 2e: Stop-limit tickfill analysis",
    )

    _uv_run(
        "select_oco_reduced_core_rolling.py",
        "--config",
        f"configs/research/experiments/{sym}_oco_reduced_core_rolling_2025.yaml",
        dry_run=dry_run,
        label="Stage 2f: Reduced core rolling selection",
    )


# ---------------------------------------------------------------------------
# Stage 3: Conditional steps (tick-exact + robustness)
# ---------------------------------------------------------------------------


def _reduced_core_has_states(symbol: str) -> bool:
    """Check if the reduced core produced any qualifying states."""
    schedule = TOM_DIR / "reduced_core_rolling" / f"{symbol}_oco_reduced_state_schedule.csv"
    if not schedule.exists():
        return False
    text = schedule.read_text(encoding="utf-8").strip()
    lines = [l for l in text.splitlines() if l.strip()]
    return len(lines) > 1  # header + at least one data line


def stage_3_conditional(symbol: str, *, dry_run: bool) -> None:
    """Run tick-exact verification and robustness if reduced core passed."""
    sym = symbol.lower()
    SYM = symbol.upper()

    if not _reduced_core_has_states(SYM) and not dry_run:
        print(
            f"\n  *** {SYM} has no qualifying reduced core states — skipping tick-exact and robustness ***"
        )
        return

    # Tick-exact verification uses same config but distinct outputs
    _uv_run(
        "verify_oco_tick_exact_shortlist.py",
        "--config",
        f"configs/research/experiments/{sym}_oco_reduced_core_rolling_2025.yaml",
        "--out-summary-csv",
        f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{SYM}_oco_tick_exact_summary.csv",
        "--out-monthly-csv",
        f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{SYM}_oco_tick_exact_monthly.csv",
        "--out-state-csv",
        f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{SYM}_oco_tick_exact_state.csv",
        "--report-out",
        f"docs/analysis/{sym}_oco_tick_exact_rolling_report.md",
        dry_run=dry_run,
        label="Stage 3a: Tick-exact verification",
    )

    # Robustness analysis
    pred_path = f"data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/{SYM}_oco_monthly_predictions.parquet"
    schedule_csv = f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{SYM}_oco_reduced_state_schedule.csv"
    out_summary = (
        f"data/analysis/tick_opportunity_mining/full_robustness/{SYM}_oco_robustness_summary.csv"
    )
    out_monthly = (
        f"data/analysis/tick_opportunity_mining/full_robustness/{SYM}_oco_robustness_monthly.csv"
    )
    report_out = f"docs/analysis/{sym}_oco_monthly_wfo_robustness_fullcap_report.md"

    _uv_run(
        "analyze_oco_monthly_wfo_robustness.py",
        "--pred-path",
        pred_path,
        "--reduced-state-schedule-csv",
        schedule_csv,
        "--use-exec-selection",
        "true",
        "--execution-quantile",
        "0.9",
        "--out-summary-csv",
        out_summary,
        "--out-monthly-csv",
        out_monthly,
        "--report-out",
        report_out,
        dry_run=dry_run,
        label="Stage 3b: WFO robustness analysis",
    )


# ---------------------------------------------------------------------------
# Stage 4: Registration — patch hardcoded symbol lists and manifests
# ---------------------------------------------------------------------------


def _patch_python_symbols_tuple(script_path: Path, symbol: str, *, dry_run: bool) -> None:
    """Add symbol to a SYMBOLS = (...) tuple in a Python script."""
    text = script_path.read_text(encoding="utf-8")
    upper = symbol.upper()
    if f'"{upper}"' in text:
        print(f"  skip {script_path.name}: {upper} already present")
        return
    # Match SYMBOLS = ("EURUSD", ...) pattern
    pat = r"(SYMBOLS\s*=\s*\([^)]+)"
    m = re.search(pat, text)
    if m:
        old = m.group(1)
        new = old.rstrip() + f', "{upper}"'
        text = text.replace(old, new)
        print(
            f"  {'[DRY-RUN] ' if dry_run else ''}patch {script_path.name}: added {upper} to SYMBOLS"
        )
        if not dry_run:
            script_path.write_text(text, encoding="utf-8")
        return
    print(f"  warn: could not find SYMBOLS tuple in {script_path.name}")


def _patch_argparse_default_symbols(script_path: Path, symbol: str, *, dry_run: bool) -> None:
    """Add symbol to a --symbols default string in an argparse script."""
    text = script_path.read_text(encoding="utf-8")
    upper = symbol.upper()
    if upper in text:
        print(f"  skip {script_path.name}: {upper} already present")
        return
    # Match: default="EURUSD,GBPUSD,..." on a line with --symbols
    pat = r'(add_argument\(["\']--symbols["\'].*?default="[A-Z,]+)'
    m = re.search(pat, text, re.DOTALL)
    if m:
        old = m.group(1)
        new = old + f",{upper}"
        text = text.replace(old, new, 1)
        print(f"  {'[DRY-RUN] ' if dry_run else ''}patch {script_path.name}: added {upper}")
        if not dry_run:
            script_path.write_text(text, encoding="utf-8")
        return
    print(f"  warn: could not find default symbols in {script_path.name}")


def _patch_bible_manifest(symbol: str, *, dry_run: bool) -> None:
    """Append a new symbol block to the bible manifest YAML."""
    text = BIBLE_MANIFEST.read_text(encoding="utf-8")
    upper = symbol.upper()
    lower = symbol.lower()
    if f"symbol: {upper}" in text:
        print(f"  skip bible manifest: {upper} already present")
        return

    block = f"""
  - symbol: {upper}
    reduced_summary_csv: data/analysis/tick_opportunity_mining/reduced_core_rolling/{upper}_oco_reduced_summary.csv
    tick_exact_summary_csv: data/analysis/tick_opportunity_mining/reduced_core_rolling/{upper}_oco_tick_exact_summary.csv
    robustness_summary_csv: data/analysis/tick_opportunity_mining/full_robustness/{upper}_oco_robustness_summary.csv
    edge_velocity_csv: ""
    stop_limit_summary_csv: data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/summary.csv
    mining_report_md: docs/analysis/{lower}_tick_opportunity_mining_report.md
    wfo_report_md: docs/analysis/{lower}_tick_opportunity_monthly_wfo_oco_fullcap_report.md
    reduced_core_report_md: docs/analysis/{lower}_oco_reduced_core_rolling_report.md
    tick_exact_report_md: docs/analysis/{lower}_oco_tick_exact_rolling_report.md
    robustness_report_md: docs/analysis/{lower}_oco_monthly_wfo_robustness_fullcap_report.md
"""

    # Insert before `required_artifacts:` section
    insertion_point = "required_artifacts:"
    if insertion_point in text:
        text = text.replace(insertion_point, block + insertion_point)
    else:
        text += block

    print(f"  {'[DRY-RUN] ' if dry_run else ''}patch bible manifest: added {upper}")
    if not dry_run:
        BIBLE_MANIFEST.write_text(text, encoding="utf-8")


def _patch_mkdocs_nav(symbol: str, *, dry_run: bool) -> None:
    """Add symbol to the mkdocs.yml navigation."""
    text = MKDOCS_YML.read_text(encoding="utf-8")
    upper = symbol.upper()
    lower = symbol.lower()
    if f"{lower}_tick_opportunity_mining_report.md" in text:
        print(f"  skip mkdocs.yml: {upper} already present")
        return

    # Build nav entries — only include reports that the pipeline actually creates
    # Mining and WFO reports are always created; downstream reports are conditional
    docs_root = ROOT / "docs" / "analysis"
    entries = [f"        - Mining: analysis/{lower}_tick_opportunity_mining_report.md"]
    entries.append(
        f"        - WFO Fullcap: analysis/{lower}_tick_opportunity_monthly_wfo_oco_fullcap_report.md"
    )

    if (docs_root / f"{lower}_oco_reduced_core_rolling_report.md").exists():
        entries.append(
            f"        - Reduced Core: analysis/{lower}_oco_reduced_core_rolling_report.md"
        )

    if (docs_root / f"{lower}_oco_tick_exact_rolling_report.md").exists():
        entries.append(
            f"        - Tick-Exact Rolling: analysis/{lower}_oco_tick_exact_rolling_report.md"
        )
    if (docs_root / f"{lower}_oco_monthly_wfo_robustness_fullcap_report.md").exists():
        entries.append(
            f"        - WFO Robustness: analysis/{lower}_oco_monthly_wfo_robustness_fullcap_report.md"
        )

    nav_block = f"      - {upper}:\n" + "\n".join(entries)

    # Insert before the "Governance + Audit:" section
    marker = "  - Governance + Audit:"
    if marker in text:
        text = text.replace(marker, nav_block + "\n" + marker)
    else:
        # Fallback: insert before "Repository Notes:"
        marker2 = "  - Repository Notes:"
        if marker2 in text:
            text = text.replace(marker2, nav_block + "\n" + marker2)

    print(f"  {'[DRY-RUN] ' if dry_run else ''}patch mkdocs.yml: added {upper} nav entries")
    if not dry_run:
        MKDOCS_YML.write_text(text, encoding="utf-8")


def stage_4_registration(symbol: str, *, dry_run: bool) -> None:
    """Patch all hardcoded symbol lists and config files."""
    print("\n=== Stage 4: Registration ===")
    _uv_run(
        "freeze_oco_live_governance.py",
        "--symbols",
        symbol,
        dry_run=dry_run,
        label="Stage 4a: Freeze live governance lock",
    )

    _patch_python_symbols_tuple(CATALOG_SCRIPT, symbol, dry_run=dry_run)
    _patch_argparse_default_symbols(DRIFT_SCRIPT, symbol, dry_run=dry_run)
    _patch_argparse_default_symbols(THRESHOLD_SCRIPT, symbol, dry_run=dry_run)
    _patch_argparse_default_symbols(
        ROOT / "scripts" / "audit_oco_leakage_label_integrity.py", symbol, dry_run=dry_run
    )
    _patch_bible_manifest(symbol, dry_run=dry_run)
    _patch_mkdocs_nav(symbol, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Stage 5: Docs Rebuild
# ---------------------------------------------------------------------------


def stage_5_docs(*, dry_run: bool) -> None:
    """Run the full docs-contract and docs-build pipeline."""
    _run(["make", "docs-contract"], dry_run=dry_run, label="Stage 5a: Docs contract")
    _run(
        ["uv", "run", "mkdocs", "build", "--strict"],
        dry_run=dry_run,
        label="Stage 5b: MkDocs build",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(
        description="End-to-end symbol onboarding: HistData -> validated docs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run for USDCAD:
  uv run python scripts/onboard_symbol.py --symbol USDCAD --months 201801-202602

  # Dry-run to see what would happen:
  uv run python scripts/onboard_symbol.py --symbol USDCAD --months 201801-202602 --dry-run

  # Skip data download (tick bars already built):
  uv run python scripts/onboard_symbol.py --symbol USDCAD --skip-data

  # Force re-download and rebuild everything:
  uv run python scripts/onboard_symbol.py --symbol USDCAD --months 201801-202602 --force
""",
    )
    p.add_argument("--symbol", required=True, help="Symbol to onboard, e.g. USDCAD")
    p.add_argument(
        "--months",
        default="",
        help="YYYYMM range or list, e.g. 201801-202602 or 201801,201802,...",
    )
    p.add_argument("--skip-data", action="store_true", help="Skip Stage 0 (data acquisition)")
    p.add_argument("--skip-ml", action="store_true", help="Skip Stage 2 (ML pipeline)")
    p.add_argument("--skip-docs", action="store_true", help="Skip Stage 5 (docs rebuild)")
    p.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    p.add_argument("--force", action="store_true", help="Force re-download/rebuild all stages")
    p.add_argument("--model-export-dir", default=None, help="Directory to export .cbm models + .json thresholds")
    args = p.parse_args()

    symbol = str(args.symbol).strip().upper()
    if not re.fullmatch(r"[A-Z]{6,10}", symbol):
        print(f"error: invalid symbol: {symbol}")
        sys.exit(1)

    # Parse months
    months_str = str(args.months).strip()
    if not months_str and not args.skip_data:
        print("error: --months required unless --skip-data is set")
        sys.exit(1)

    if "-" in months_str and "," not in months_str:
        # Range format: 201801-202602
        parts = months_str.split("-")
        if len(parts) == 2:
            months_list = _months_range(parts[0], parts[1])
            months_str = ",".join(months_list)

    print("╔══════════════════════════════════════════╗")
    print(f"║  Onboarding {symbol:<28s} ║")
    print("╚══════════════════════════════════════════╝")
    if args.dry_run:
        print("  MODE: dry-run (no commands will execute)")
    print()

    # Stage 0
    if not args.skip_data:
        stage_0_data(symbol, months_str, dry_run=args.dry_run, force=args.force)
    else:
        print("\n  --- Stage 0 skipped (--skip-data) ---")

    # Stage 1
    print("\n=== Stage 1: Config Cloning ===")
    stage_1_configs(symbol, dry_run=args.dry_run, force=args.force)

    # Stage 2
    if not args.skip_ml:
        stage_2_ml_pipeline(symbol, model_export_dir=args.model_export_dir, dry_run=args.dry_run)
    else:
        print("\n  --- Stage 2 skipped (--skip-ml) ---")

    # Stage 3
    stage_3_conditional(symbol, dry_run=args.dry_run)

    # Stage 4
    stage_4_registration(symbol, dry_run=args.dry_run)

    # Stage 5
    if not args.skip_docs:
        stage_5_docs(dry_run=args.dry_run)
    else:
        print("\n  --- Stage 5 skipped (--skip-docs) ---")

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}✅ Onboarding complete for {symbol}")


if __name__ == "__main__":
    main()
