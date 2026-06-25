# Path-geometry Phase B results

## B0 pre-screen: {'1h': False, '2h': True, '3h': False, '4h': False}  -> survivors ['2h']

### 2h n_bars=1: base=+1.26 geom=+1.17 diff=-0.13 day_t=-0.82 day_p=0.4119 pos=2/5 boot95=[-0.22,+0.12] null_diff=-0.16 cells={(None, 4.0), (2.0, 4.0), (2.0, None), (None, None), (3.0, None), (1.5, None), (2.0, 3.0), (None, 2.0), (3.0, 2.0)}
### 2h n_bars=2: base=+1.22 geom=+1.22 diff=-0.02 day_t=-0.16 day_p=0.8712 pos=2/5 boot95=[-0.18,+0.17] null_diff=-0.22 cells={(None, 4.0), (None, None), (3.0, None), (None, 3.0), (2.0, 3.0), (3.0, 3.0), (None, 2.0), (3.0, 2.0)}

## BH-FDR across 2 cells (q=0.05): 2h/1bar=keep-null, 2h/2bar=keep-null

> **CAVEAT (added post-hoc):** the B0 "only 2h shifts" cross-timeframe claim is an ARTIFACT — disjoint truncate-from-epoch bars give only ~4 in-session bars/day at 3h/4h, and 24-bar feature windows over nightly contig breaks decimate the panel (3h/4h panel ~2171 vs 2h ~8689). 3h/4h were never validly tested here. Superseded by the uniform 1h-grid horizon re-test (horizon_retest_results.md), which fairly tests all horizons and finds intraday tail-long NO_GO across 1-4h. The 2h-specific geometry NO_GO below is unaffected and stands.
