# ERA Microstructure Edge Brainstorm — 2026-06-05

## Context
- Directional 100-tick scalping on EURUSD: ~coin-flip, spread kills it (PR #280).
- Range-harvest maker-bracket: near-breakeven (−0.015 vs −0.59 baseline, PR #281).
- Cross-symbol residual (XS atomic lattice): −0.592 pips/trade, weak.
- The only robust family in the entire system so far is **reverse-directional**.

## Opportunity
The `tick_velocity` parquet already contains **~15 computed microstructure columns that are NOT in the `WHITELIST`**. The PUCT generator cannot use what it cannot see. Enriching the whitelist + adding literature-backed operators is the cheapest high-leverage move before building raw-tick features from scratch.

## Missing microstructure columns (already in parquet, not in WHITELIST)
| Column | Literature basis | Why it matters |
|--------|------------------|----------------|
| `signed_flow_24` | Cont-Kukanov-Stoikov OFI | Signed volume imbalance predicts short-horizon continuation in FX. |
| `directional_persistence_8` | Time-series momentum microstructure | Serial correlation of bar signs; high = momentum regime, low = mean-reversion regime. |
| `intra_bar_momentum` | Price-path / high-frequency trend | Whether price moved mostly early or late in the bar; late move = informed flow. |
| `quote_revision_rate_z` | Easley-O'Hara informed trading proxy | High quote churn = more information arrival; trade with the recent move. |
| `vol_cluster_score` | HAR-RV / Corsi volatility clustering | Predictable vol regimes; high clustering = better risk-adjusted signals. |
| `slip_proxy_pips` | Roll-spread / effective cost proxy | When slip is high, effective spread is wide → gate trades out. |
| `session_marker` | Ito-Lyons-Melvin session effects | Tokyo/London/NY have different liquidity and directional drift. |
| `hl_pos_frac` / `hl_first_mean_24` | High-low position (barzykin) | Where in the bar the close sits; extreme = exhaustion / reversal. |
| `range_pips` | Parkinson realized range | More efficient volatility estimator than close-close; wider range = more noise. |

## Four literature-backed signal directions

### 1. Signed-flow momentum with microstructure gating
**Core idea:** `signed_flow_24` predicts continuation at 1-bar horizon (Cont et al. 2014, ECB FX microstructure studies). Trade it ONLY when spread is tight and volatility is clustered (predictable).
- Base: `signed_flow_24` EWMA
- Gate: `spread_z <= 0` AND `vol_cluster_score > 0` (calm but clustered)
- Smoothing: EWMA(α=0.15)
- Normalization: `vol_scale` using `range_pips`

### 2. Regime-conditioned reversion (Roll + Bandi-Russell)
**Core idea:** When `slip_proxy_pips` is high OR `spread_z` is wide, price bounce (Roll effect) dominates. Fade the bar return only in high-noise regimes. In low-noise regimes, do nothing.
- Base: `−bar_return_sign` (simple mean-reversion)
- Gate: `slip_proxy_pips > np.nanmedian(slip_proxy_pips)` OR `spread_z > 0.5`
- Smoothing: trailing mean of `−bar_return_sign`
- Normalization: `proportional_dispersion` (range-based)

### 3. Quote-revision continuation (Easley-O'Hara informed flow)
**Core idea:** High `quote_revision_rate_z` signals informed traders are active. Trade in the direction of `intra_bar_momentum` when quote churn is elevated.
- Base: `intra_bar_momentum * quote_revision_rate_z`
- Gate: `quote_revision_rate_z > np.nanpercentile(quote_revision_rate_z, 75)`
- Smoothing: none (already bar-level)
- Normalization: `vol_scale`

### 4. Lead-lag cross-symbol (Hasbrouck price discovery)
**Core idea:** Not residual, but temporal lead-lag. If GBPUSD moves and EURUSD hasn't caught up yet, trade EURUSD in GBPUSD's direction. This is a DIFFERENT operator family than the residual lattice.
- Base: `corr_weighted_graph` of peer **returns** (not levels), using a short lag window.
- Gate: `asia_session` OFF (only liquid London/NY hours)
- Smoothing: EWMA of lagged peer return
- Normalization: `vol_scale`

## Implementation plan
1. **Whitelist expansion** — add the 9 missing columns to `WHITELIST` in `load_splits.py`.
2. **New atomic operators** — create `scripts/era_scalp/micro_atomic_concepts.py` with operators using the new columns.
3. **Seed compositions** — write 8 literature-backed seed compositions combining the new operators.
4. **Smoke search** — run `era_xs.py --atomic` on EURUSD 100-tick with budget=80 and report the best score.
5. **If smoke < 0**: pivot to building **raw-tick VPIN / Amihud / Kyle-lambda** from `data/tick_bars/` as alternative data.

## Why this could work
- The range-harvest was already −0.015 (almost flat). Adding signed-flow and quote-revision features gives the generator a causal, directional signal that is **orthogonal** to the price-level residual it was using before.
- The cross-symbol residual tried to predict **fair price**; the microstructure approach predicts **next-bar direction** using order-flow proxies.
- All features are **causal** (backward-looking bar aggregates), so the causality probe will pass.

## Risks
- `signed_flow_24` may be a noisy proxy (it uses Lee-Ready tick inference, which has errors).
- Quote revision rate may not predict direction, only volatility.
- The edge may still be < 0 after realistic cost, but if it improves from −0.59 to −0.1, that's progress toward breakeven and a deployable signal may be one feature-engineering step away.
