"""Inspect BASE predictions per symbol."""
import sys
from pathlib import Path
import polars as pl
import pandas as pd

_REPO = Path('/Users/danielfisher/repositories/behemoth/.claude/worktrees/feat-pf-15m')
sys.path.insert(0, str(_REPO))
import importlib.util
spec = importlib.util.spec_from_file_location("diag", str(_REPO / "scripts/fx_coint/interaction_ridge_diagnostic.py"))
diag = importlib.util.module_from_spec(spec)
sys.modules["diag"] = diag
spec.loader.exec_module(diag)
build_freq_bars = diag.build_freq_bars
build_panel_interactive = diag.build_panel_interactive
wfo_variant = diag.wfo_variant

for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
    src = Path(f'/Users/danielfisher/repositories/behemoth/data/tick_bars/{sym}_1m_flow.parquet')
    if not src.exists():
        continue
    df_1m = pl.read_parquet(src)
    bars = build_freq_bars(df_1m, '2h')
    panel = build_panel_interactive(bars, 'BASE')
    feat_cols = panel['feature_cols'].iloc[0]
    preds = wfo_variant(panel, feat_cols)
    preds['net'] = preds['act'] - 0.7  # rough cost
    preds['hour'] = preds['bucket'].dt.hour
    preds['year'] = preds['bucket'].dt.year

    print(f'\n=== {sym} BASE ===')
    print(f'n predictions: {len(preds)}')
    print('\nBy hour:')
    for hr in sorted(preds['hour'].unique()):
        sub = preds[preds['hour'] == hr]
        print(f"  {hr:02d}: n={len(sub):4d} net_mean={sub['net'].mean():+7.2f} act_mean={sub['act'].mean():+7.2f}")

    print('\nBy year:')
    for yr in sorted(preds['year'].unique()):
        sub = preds[preds['year'] == yr]
        print(f"  {yr}: n={len(sub):4d} net_mean={sub['net'].mean():+7.2f}")

    # Check the 14:00 predictions specifically
    p14 = preds[preds['hour'] == 14]
    if len(p14) > 0:
        print('\n  At 14:00 by year:')
        for yr in sorted(p14['year'].unique()):
            sub = p14[p14['year'] == yr]
            print(f"    {yr}: n={len(sub):3d} net_mean={sub['net'].mean():+7.2f} act_mean={sub['act'].mean():+7.2f}")
