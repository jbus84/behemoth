"""Inspect BASE model prediction timing."""
import sys
from pathlib import Path
import polars as pl
import pandas as pd

_REPO = Path('/Users/danielfisher/repositories/behemoth/.claude/worktrees/feat-pf-15m')
sys.path.insert(0, str(_REPO))

# Manually import the functions from the diagnostic script to avoid package issues
import importlib.util
spec = importlib.util.spec_from_file_location("diag", str(_REPO / "scripts/fx_coint/interaction_ridge_diagnostic.py"))
diag = importlib.util.module_from_spec(spec)
sys.modules["diag"] = diag
spec.loader.exec_module(diag)
build_freq_bars = diag.build_freq_bars
build_panel_interactive = diag.build_panel_interactive
wfo_variant = diag.wfo_variant

src = Path('/Users/danielfisher/repositories/behemoth/data/tick_bars/EURUSD_1m_flow.parquet')
df_1m = pl.read_parquet(src)
bars = build_freq_bars(df_1m, '2h')
panel = build_panel_interactive(bars, 'BASE')
feat_cols = panel['feature_cols'].iloc[0]
preds = wfo_variant(panel, feat_cols)
print('=== EURUSD BASE ===')
print('n predictions:', len(preds))
print('\nPredictions by hour:')
print(preds['bucket'].dt.hour.value_counts().sort_index().to_string())
print('\nPredictions by year:')
print(preds['bucket'].dt.year.value_counts().sort_index().to_string())
print('\nEarliest:', preds['bucket'].min())
print('Latest:  ', preds['bucket'].max())

# Check the top predictions specifically at 14:00
preds_14 = preds[preds['bucket'].dt.hour == 14]
print('\n=== At 14:00 specifically ===')
print('Count:', len(preds_14))
print('By year:')
print(preds_14['bucket'].dt.year.value_counts().sort_index().to_string())

# Check the actual prediction mu values at 14:00 vs other hours
print('\nmu distribution by hour (mean of top-5% preds):')
for hr in sorted(preds['bucket'].dt.hour.unique()):
    sub = preds[preds['bucket'].dt.hour == hr]
    print(f"  {hr:02d}: n={len(sub)}, mu_mean={sub['mu'].mean():.3f}, mu_std={sub['mu'].std():.3f}")
