# FX edge hunt + diversification — session log (2026-06-26)

**Branch:** `feat/fx-shortterm-55`  ·  **Pool:** 5 non-JPY majors (JPY added where noted)
·  **Data:** `data/tick_bars/{sym}_{1000tick,1h_flow}.parquet`  ·  **Cost:** 1.0 bp round-trip
·  All results: causal walk-forward, non-overlapping trades, real cost, folds+/sym+ gauntlet.

## TL;DR
Spot-FX signal space mapped exhaustively. **Reversion is the only monetizable driver**,
in two mutually-orthogonal forms that diversify each other:
- **TS price reversion** — fade `ffd_zvol20` (fractional-diff), triple-barrier first-touch, N=50.
- **XS residual reversion** — cross-sectional dollar-neutral, USD factor removed.

Best portfolio: **TB(N=50) + XS, ~60/40**, Calmar 0.47, maxDD −14.1 (unit-vol), 8/9 yrs.
Edge sharpened this session: **fade the top 1% extension (q0.99), not top 10%** → net
+1.10 / 5-of-5 symbols. Everything else tested is sub-cost, dead, or needs other data.

## 1. The diversification win — XS reversion complements TB
- `xs_reversion.py`: demean 6 majors' currency-vs-USD daily returns → fade rolling-L
  residual, dollar-neutral. Cost-robust at L=20: full-cost Sharpe 0.23, 8/9 yrs, maxDD
  −660 bps. Structurally orthogonal to USD direction.
- `xs_plus_tbreal_portfolio.py`: vs the **real** TB book (1000-tick `ffd_zvol20` triple-barrier
  fade — not the daily weekly fade, which is net-negative under cost), corr **+0.10**; 50/50
  unit-vol blend cuts maxDD ~40% (−27.8 → −16.7), lifts pos-years 6/9 → 8/9 (XS rescues
  TB's 2024 −3.0 → +1.9).
- `xs_tb_blend_opt.py`: longer TB N strictly better; optimum **N=50 + ~40% XS** → Calmar
  0.47 (vs 0.40 TB-alone), on a flat plateau (not an overfit spike).

## 2. Edge sharpening — extreme-move thresholding (`extreme_move_probe.py`)
Fade `ffd_zvol20` @N=50 by extension quantile:
| q | net | sym+ | hit |
|---|---|---|---|
| 0.90 (top 10%) | +0.92 | 4/5 | 0.517 |
| **0.99 (top 1%)** | **+1.10** | **5/5** | 0.518 |
| 0.995 | −0.74 | 4/5 | 0.513 |
| 0.999 | −0.76 | 1/5 | **0.484** |

**Reversion is a mid-tail phenomenon with a magnitude ceiling:** top 1% is the sweet
spot; beyond ~top 0.5% it breaks down and the very largest moves *continue* (hit < 0.50,
momentum-ignition regime). Actionable: set TB threshold to ~q0.99.

## 3. Continuation structure (`continuation_probe.py`, `reversion_plus_continuation.py`)
"Before reversion there must be continuation" — true structurally, not monetizable:
- Crossover map: price-change signals (bar_return/ffd_vel/macd) **revert at every horizon**
  (overshoot is intrabar); only `intra_bar_mom` **continues** at all N (+0.07→+0.23,
  orthogonal sign). Two simultaneous forces: level reverts, intrabar drift persists.
- Continuation is real + callable (hit 0.517 > 0.50) but sub-cost (gross ~0.28 < 1bp),
  and adding it to the reversion model *degrades* it (REV-only +0.74 → REV+CONT −0.12).

## 4. Orthogonal-driver sweep — all NO-GO at retail cost
| driver | script | verdict |
|---|---|---|
| XS momentum | `xs_momentum.py` | dead; residual space mean-reverts at all L (corr −1.0 to XS rev) |
| Hour-of-day / session | `orthogonal_screen.py`, `session_seasonality_timebars.py` | orthogonal (corr ≈0) but sub-cost on both clocks |
| Range breakout | `orthogonal_screen.py` | reverts (reversion everywhere) |
| Gap reversion | `orthogonal_screen.py` | tiny / illiquid |
| Flow imbalance (flow_tick/OFI) | `flow_imbalance_probe.py` | IC ≈0, dead |
| `ffd_0.1` as 2nd FFD leg | `tb_multisignal_blend.py` | corr 0.55–0.59, lowers Calmar — no value |
| All non-FFD features (N=10/20/50) | `tb_feature_edges.py` | only FFD family BH-sig + positive net |

## 5. Conclusion & next
- **Monetizable spot-FX edge = reversion only**, two orthogonal forms (now in the book).
- Momentum/continuation/seasonality/flow/breakout/carry all sub-cost or need other data.
- **Next real breadth = out-of-asset** (index/rate futures, or the crypto order-flow XS
  signal that showed OOS gross predictability). Within FX, remaining work is
  optimization/sizing: re-blend with the q0.99 threshold, then size to the 10% max-DD /
  $100k budget for a deployable %-return.

Scripts (this branch): `xs_reversion`, `xs_momentum`, `xs_plus_tb*`, `xs_tb_blend_opt`,
`tb_feature_edges`, `tb_multisignal_blend`, `orthogonal_screen`, `hour_seasonality`,
`session_seasonality_timebars`, `flow_imbalance_probe`, `continuation_probe`,
`reversion_plus_continuation`, `extreme_move_probe` (+ st55_* from the prior thread).
