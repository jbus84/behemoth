#!/usr/bin/env python3
import glob, sys
sys.path.insert(0, '/Users/danielfisher/repositories/behemoth/.claude/worktrees/era-tuned-search')
from scripts.era_scalp.run_era_eur import build_trade_splits, SYMBOL_DEFAULT
from scripts.era_scalp.cost_aware_score import CostAwarePerSymbolScorer
from pathlib import Path

sp = build_trade_splits(SYMBOL_DEFAULT, Path('data/analysis/tick_velocity') / f'{SYMBOL_DEFAULT}_100tick_velocity.parquet')
scorer = CostAwarePerSymbolScorer(sp, SYMBOL_DEFAULT)

files = sorted(glob.glob('/tmp/era_eur_cache/branch_regime_switching_*.py'))
print(f'Found {len(files)} regime_switching programs', file=sys.stderr)

best_val = -1e9
best_file = None
for i, f in enumerate(files):
    src = open(f).read()
    try:
        v, mean, se, lg = scorer.score(src, 'validation')
        if v > best_val:
            best_val = v
            best_file = f
            print(f'[{i+1}/{len(files)}] NEW BEST: {f} val={v:+.3f}', file=sys.stderr)
    except Exception as e:
        pass

if best_file:
    print(f'BEST: {best_file} val={best_val:+.3f}', file=sys.stderr)
    src = open(best_file).read()
    with open('/tmp/winner_regime_switching.py', 'w') as out:
        out.write(src)
    print('Saved to /tmp/winner_regime_switching.py', file=sys.stderr)
    print(src)
else:
    print('No valid regime_switching programs found', file=sys.stderr)
