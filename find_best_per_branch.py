#!/usr/bin/env python3
import glob, sys, json
sys.path.insert(0, '/Users/danielfisher/repositories/behemoth/.claude/worktrees/era-tuned-search')
from scripts.era_scalp.run_era_eur import build_trade_splits, SYMBOL_DEFAULT
from scripts.era_scalp.cost_aware_score import CostAwarePerSymbolScorer
from pathlib import Path

sp = build_trade_splits(SYMBOL_DEFAULT, Path('data/analysis/tick_velocity') / f'{SYMBOL_DEFAULT}_100tick_velocity.parquet')
scorer = CostAwarePerSymbolScorer(sp, SYMBOL_DEFAULT)

branches = ['liquidity_gate', 'flow_intensity', 'transient_impact', 'asymmetric_vol', 'regime_switching']
results = {}
for branch in branches:
    files = sorted(glob.glob(f'/tmp/era_eur_cache/branch_{branch}_*.py'))
    best_val = -1e9
    best_file = None
    for f in files:
        src = open(f).read()
        try:
            v, mean, se, lg = scorer.score(src, 'validation')
            if v > best_val:
                best_val = v
                best_file = f
        except Exception:
            pass
    if best_file:
        results[branch] = {'file': best_file, 'val': float(best_val)}
        print(f'{branch}: {best_file} val={best_val:+.3f}', file=sys.stderr)
    else:
        print(f'{branch}: no valid programs found', file=sys.stderr)

with open('/tmp/best_per_branch.json', 'w') as out:
    json.dump(results, out)
print('Saved to /tmp/best_per_branch.json', file=sys.stderr)
