# Strategy Master Manual (M5/M15) — Kalman + Rule‑Based MOM

**Version**: 7.0  
**Date**: February 2026  
**Status**: Rule‑based inference with mandatory guardrail

[!IMPORTANT]
This strategy **does not use any ML model**. All decisions are rule‑based on the Kalman Z‑score signal and the loss‑streak guardrail.

**Repo structure (production)**
- Core logic: `src/behemoth/`
- Deterministic runs: `pipelines/`
- Thin wrappers: `scripts/`

---

## Executive Summary
This manual defines the production research strategy for the 5‑minute (M5) and 15‑minute (M15) systems. The strategy is **MOM‑only** and **rule‑based**:

1. **Kalman scout** computes a rolling Z‑score on the spread (M5/M15 use 750‑bar lookback).
2. **MOM entry** triggers when `|Z| >= 1.5` (both signs allowed).
3. **Exit** when Z crosses 0 (mean‑reversion) or when `|Z| > 4.0` (momentum stop).
4. **Guardrail (mandatory)**: per‑symbol loss‑streak >= 3 triggers a **7‑day pause**.

This guardrail produces large drawdown reductions on both M5 and M15 while preserving positive expectancy.  
For **M5 and M15**, WFO‑optimized parameters are now treated as the **production defaults**.

**M15 WFO calibration (Feb 2026)**  
We also ran a **full‑parameter walk‑forward optimization (WFO)** on M15. The best parameters were **stable across all folds**:
- `z_entry = 1.5`, `z_stop = 4.0`, `z_lookback = 750`
- Guardrail: `loss_streak = 3`, `cooldown = 7 days`

These are the **recommended production parameters for M15**.

**M5 WFO calibration (Feb 2026)**  
We ran the same full‑parameter WFO on M5. The best parameters were **stable across all folds**:
- `z_entry = 1.5`, `z_stop = 4.0`, `z_lookback = 750`
- Guardrail: `loss_streak = 3`, `cooldown = 7 days`

These are the **recommended production parameters for M5**.

---

## Strategy Overview (High‑Level)
The system trades synthetic spreads between asset pairs. A Kalman filter estimates a hedge ratio, then a rolling Z‑score of the spread residual triggers MOM entries. The active leg is chosen by the beta band (`beta < 0.98 => Y`, `beta > 1.02 => X`).

**Signal Summary**
- Entry (MOM): `|Z| >= 1.5`
- Exit:
  - **Loss / mean reversion**: Z crosses 0
  - **Win / momentum stop**: `|Z| > 4.0`
- Timeout: 500 bars
- Minimum gap between entries: 20 bars

**Required Risk Control**
- **Loss‑streak guardrail**: if a symbol has 3 consecutive losses, skip all its signals for 7 days.

---

## Detailed Strategy (How It Works)
This section is an exact, rule‑based specification.

### 1) Kalman Scout and Z‑Score
- Inputs: log prices `y = log(Y)`, `x = log(X)`
- Level Kalman filter estimates a rolling hedge ratio on mean‑centered prices.
- Spread error: `(y - mu_y) - beta * (x - mu_x)`
- Z‑score uses a rolling mean/std of spread error.
  - **M5/M15 WFO‑recommended**: 750 bars

### 2) Active‑Leg Selection
- If `beta < 0.98`: **active leg = Y**
- If `beta > 1.02`: **active leg = X**
- Otherwise skip (neutral zone)

### 3) MOM Entry
- Entry when `|Z| >= 1.5`.
- Direction follows Z sign:
  - `Z > 0` → LONG spread on active leg
  - `Z < 0` → SHORT spread on active leg

### 4) Exit Logic (Z‑Based)
- **Loss / mean‑reversion**: Z crosses 0
- **Win / momentum stop**: `|Z| > 4.0` (M5/M15 WFO defaults)
- **Timeout**: 500 bars

### 5) Loss‑Streak Guardrail (Mandatory)
Per symbol:
- Track consecutive losses (trade‑level).
- If **loss‑streak >= 3**, pause the symbol for **7 calendar days** (M5/M15 WFO defaults).
- After cooldown, trading resumes and streak resets.

Loss streak is computed from **PnL sign** (`pnl_bps <= 0` counts as a loss). **Win rate is not a KPI**; the sign of PnL is used only to enforce the guardrail.

This guardrail is **required at runtime**. Without it, drawdowns are materially larger.

---

## Strategy Plots (Guardrail Impact)
**Monthly Net PnL (Baseline vs Guardrail)**
- M5: `docs/figures/m5_guardrail_monthly_net.png`
- M15: `docs/figures/m15_guardrail_monthly_net.png`

**Drawdown Curves (Baseline vs Guardrail)**
- M5: `docs/figures/m5_guardrail_drawdown.png`
- M15: `docs/figures/m15_guardrail_drawdown.png`

---

## Results (Guardrail vs Baseline, WFO Defaults)
Results are **gross, cost‑free**, and computed over 2018–2025 using the WFO‑recommended parameters.
All reported performance stats use **PnL‑based win/loss** (`pnl_bps > 0`). The `outcome` label is a **signal outcome** (Z‑barrier logic) and is **not used** for performance reporting.

### M5 (MOM‑only)
- Baseline: 189,744 trades, mean 2.93 bps, max DD ‑64,432 bps, Sharpe 0.57
- Guardrail: 58,853 trades, mean 24.22 bps, max DD ‑11,124 bps, Sharpe 5.82

### M15 (MOM‑only)
- Baseline: 63,046 trades, mean 5.59 bps, max DD ‑52,495 bps, Sharpe 0.90
- Guardrail: 36,780 trades, mean 44.65 bps, max DD ‑6,087 bps, Sharpe 5.07

### M15 (WFO‑recommended parameters, guardrail applied)
WFO parameters: `z_entry=1.5`, `z_stop=4.0`, `z_lookback=750`, guardrail `loss_streak=3`, `cooldown=7d`.
- Trades: 36,780
- Mean: 44.65 bps
- Total: 1,642,140 bps
- Max DD: ‑6,087 bps
- Sharpe (daily): 5.07; Sharpe (active): 5.86; Sharpe (trade): 19.40

### M5 (WFO‑recommended parameters, guardrail applied)
WFO parameters: `z_entry=1.5`, `z_stop=4.0`, `z_lookback=750`, guardrail `loss_streak=3`, `cooldown=7d`.
- Trades: 58,853
- Mean: 24.22 bps
- Total: 1,425,522 bps
- Max DD: ‑11,124 bps
- Sharpe (daily): 5.82; Sharpe (active): 6.52; Sharpe (trade): 22.36

---

## Additional Integrity Checks (Feb 2026)
These checks validate robustness beyond core performance.

**Reproducibility manifest (data + config fingerprint)**
We generate a reproducibility manifest that fingerprints data files, config values, and git state:
- Script: `scripts/build_repro_manifest.py`
- Output: `data/analysis/repro_manifest.json`
This is the source of truth for exact re‑runs and audit trails.

**Exit logic causality (no look‑ahead in exits)**
Exit logic is tested to confirm it only uses data up to the exit bar (future bars do not alter exit timing).
Tests:
- `tests/test_exit_causality.py`
- `tests/test_simulate_trade.py`

**Time‑alignment stress test (±1 bar shift)**
We shift one leg by ±1 bar and recompute MOM trades to measure sensitivity to alignment errors.
Outputs:
- `data/analysis/m5_alignment_sensitivity.csv`
- `data/analysis/m15_alignment_sensitivity.csv`
These files include `stride` and `max_bars` columns so any sampling is explicit. Set both to full (stride=1, max_bars=0) for final runs.
Conclusion: alignment errors should degrade performance; this test is a canary for timestamp drift.

**Time‑weighted vs trade‑level drawdown**
Daily equity curve drawdown can differ materially from trade‑level DD.
- M5: trade‑level DD ‑119,032 bps vs daily DD ‑67,618 bps (ratio 0.57)
- M15: trade‑level DD ‑31,466 bps vs daily DD ‑39,926 bps (ratio 1.27)

**Guardrail timing sensitivity (entry‑ordered vs exit‑ordered)**
Loss‑streak guardrail should be applied by **exit time**. Applying it by entry time reduces mean PnL.
- M5: entry‑ordered mean ‑1.58 bps vs exit‑ordered; trade count ‑6.65%
- M15: entry‑ordered mean ‑4.02 bps vs exit‑ordered; trade count ‑4.10%

**Timeout convention (entry+499 vs entry+500)**
Timeouts are implemented at `entry_idx + 499` when `duration_bars = 500`. Impact is negligible.
- M5: mean delta ‑0.125 bps, flip rate 0.33% (n=2,732)
- M15: mean delta +0.047 bps, flip rate 0.92% (n=976)

**Outlier‑bar dependency (8σ bars)**
Outlier removal materially reduces edge, even with guardrail applied.
- M5: guardrail mean 13.56 → 11.17 bps when removing outlier‑overlap trades
- M15: guardrail mean 28.88 → 23.09 bps when removing outlier‑overlap trades
Conclusion: outlier bars contribute materially to profits; guardrail does not eliminate this dependency.

**Tail‑risk controls (extreme trade frequency)**
A rolling tail‑frequency guardrail (extreme trades in last 50) does **not** improve robustness.
- M5: minor DD improvement only at strict settings (10%), mean declines
- M15: DD worsens at strict settings; looser settings are no‑ops
Conclusion: not recommended.

**Pair‑stability filter**
Removing pairs with negative PnL in ≥50% of years **improves mean and reduces DD**, but does not remove tail‑heavy pairs.
Conclusion: viable optional filter (see `docs/analysis/stable_pairs_whitelist.md`).

**Execution delay sensitivity (resimulated exits)**
Delaying entry by 1–3 bars and **re‑simulating Z‑exits** does **not** materially degrade performance.
- M5: mean improves modestly (baseline 0.87 → ~1.18–1.19 bps), DD slightly improves
- M15: mean roughly stable (baseline 4.97 → ~4.82–4.96 bps)
Guardrail performance remains strong under delayed entry.
Conclusion: the signal appears early rather than late; delays do not break the edge.

**Fill‑price realism (entry/exit mechanics)**
We explicitly test entry at close/next close/mean and apply proportional slippage to exits.
Outputs:
- `data/analysis/m5_fill_price_sensitivity.csv`
- `data/analysis/m15_fill_price_sensitivity.csv`

**Portfolio constraints**
Caps on max concurrent trades or per‑leg exposure **reduce performance** materially, both with and without guardrail. Not recommended.

**Stress tests**
- Removing 2020 improves baseline DD modestly; guardrail remains strong.
- Year‑bootstrap (200 samples) shows guardrail mean PnL remains high (p5–p95):
  - M5: ~11.96 → 17.42 bps
  - M15: ~25.56 → 33.44 bps

**Symbol stability (top‑N contributors removed)**
We removed the top 1–3 PnL‑contributing pairs and recomputed metrics:
- **Baseline** degrades rapidly as top contributors are removed.
- **Guardrail** remains strong and largely unchanged.

**M5 (top‑N removed, mean PnL bps)**
- Baseline: `0.87 → 0.34 → 0.14 → 0.02`
- Guardrail: `15.52 → 15.88 → 15.62 → 15.74`

**M15 (top‑N removed, mean PnL bps)**
- Baseline: `4.97 → 3.79 → 3.26 → 2.75`
- Guardrail: `31.82 → 29.62 → 28.08 → 26.88`

Outputs:
- `data/analysis/m5_symbol_topn_sensitivity.csv`
- `data/analysis/m15_symbol_topn_sensitivity.csv`

**Bootstrap robustness (months + trade‑block resampling)**
We ran **month‑bootstrap** and **trade‑block bootstrap** (block sizes 200/500) with **100 samples** each.
Guardrail remains robust across both resampling schemes; baseline is fragile.

**Month bootstrap (p5 / p50 / p95 mean PnL bps)**
- M5 baseline: **‑0.20 / 0.79 / 2.21**
- M5 guardrail: **13.69 / 15.15 / 16.52**
- M15 baseline: **3.17 / 5.06 / 7.53**
- M15 guardrail: **27.27 / 29.75 / 33.52**

**Trade‑block bootstrap (block size 200, p5 / p50 / p95 mean PnL bps)**
- M5 baseline: **‑0.18 / 0.88 / 1.79**
- M5 guardrail: **11.76 / 12.82 / 13.85**
- M15 baseline: **2.61 / 5.04 / 7.83**
- M15 guardrail: **23.53 / 26.70 / 29.71**

Outputs:
- `data/analysis/m5_bootstrap_month_summary.csv`
- `data/analysis/m15_bootstrap_month_summary.csv`
- `data/analysis/m5_bootstrap_tradeblock_summary.csv`
- `data/analysis/m15_bootstrap_tradeblock_summary.csv`

**Tick vs bar consistency**
Tick‑derived closes match bar closes closely for most symbols, but **XAUUSD March 2020** shows large deviations (p95 ~9 bps, max ~44 bps). This is a data‑quality risk for stressed periods.

**Tick‑gap / illiquidity sensitivity**
Removing trades that overlap large tick gaps (60–300s) **flips the edge negative** for both M5 and M15. Even with guardrail, only M5 at 300s remains modestly positive; M15 remains negative. This indicates performance depends on periods with low liquidity or data gaps.

**Feed smoothing sensitivity (tick‑level smoothing → bar rebuild, 2018–2025)**
We tested **realistic tick‑feed smoothing** and recomputed bars, signals, and trades:
- **Time throttling**: keep the last tick per **1s** and **5s** bucket
- **Price filtering**: keep ticks only after **0.5 bps** or **1.0 bps** move

**Aggregate impact (trade‑weighted delta vs baseline, fast configs only):**
- **M5**: guardrail **+0.10% mean**, **+0.07% total**; no‑guard **‑2.45% mean**, **‑2.43% total**
- **M15**: guardrail **+0.39% mean**, **+0.58% total**; no‑guard **‑0.70% mean**, **‑0.71% total**

**Regime/year sensitivity**  
Year‑level deltas are usually modest but can swing in specific years. The largest guardrail‑on swings were:
- **M5**: 2024 ~**‑19%** mean delta (trade‑weighted)
- **M15**: 2020 ~**‑114%** mean delta (trade‑weighted)

These year spikes are driven by a small number of pair/config slices with low base totals. Use the year summary files for detail.

**Most smoothing‑sensitive pairs (guardrail on, worst config by |total_delta_pct|, fast configs):**
- **M5**: AUD/CAD, CHF/JPY, GBP/CAD, NZD/CAD, Gold/Oil  
- **M15**: EUR/JPY, Gold/Silver, GBP/JPY, SPX/Dow, NZD/CAD

Files:
- `data/analysis/m5_smoothing_year_summary_fast.csv`
- `data/analysis/m15_smoothing_year_summary_fast.csv`
- `data/analysis/m5_smoothing_pair_deltas_fast.csv`
- `data/analysis/m15_smoothing_pair_deltas_fast.csv`
- `data/analysis/m5_smoothing_pair_sensitivity_fast.csv`
- `data/analysis/m15_smoothing_pair_sensitivity_fast.csv`

**Guardrail failure modes (opportunity cost)**
We measure the PnL of skipped trades to quantify opportunity cost and identify if the guardrail blocks extended positive regimes.
Outputs:
- `data/analysis/m5_guardrail_skip_stats.csv`
- `data/analysis/m15_guardrail_skip_stats.csv`
- `data/analysis/m5_guardrail_symbol_pauses.csv`
- `data/analysis/m15_guardrail_symbol_pauses.csv`

**Fill‑price sensitivity (entry/exit)**
Entry at close vs next‑close vs mean is similar, but **slippage proportional to move size** is punitive:
- Without guardrail, 5% proportional slippage turns mean PnL negative on both M5/M15.
- With guardrail, 10% proportional slippage still yields positive mean, but materially reduced (M5 ~11–12 bps, M15 ~23–24 bps).

**Why the loss‑streak guardrail works (mechanism)**
We tested the guardrail against baseline trades using the WFO defaults (`z_entry=1.5`, `z_stop=4.0`, `z_lookback=750`, loss‑streak=3, cooldown=7d).

Key findings:
- **Skipped trades are net negative**:
  - M5: 131,036 skipped trades, mean **‑5.13 bps**, win rate **36.9%**.
  - M15: 27,451 skipped trades, mean **‑39.57 bps**, win rate **25.8%**.
- **Losses cluster**: after consecutive losses, the *next* trade expectancy is strongly negative.
  - M5: after 1 loss, mean **‑13.54 bps** (WR 32%); after 2 losses, **‑24.53 bps** (WR 22%).
  - M15: after 1 loss, mean **‑23.06 bps** (WR 32%); after 2 losses, **‑42.80 bps** (WR 21.9%).
- **Loss concentration**: ~**75%** of total loss PnL comes from trades that are the **3rd loss or later** in a streak (both M5 and M15).

Conclusion: the guardrail is effective because **losses are serially correlated**. Skipping trades in these regimes removes a structurally negative conditional expectation, which is why mean PnL rises and DD collapses.

**Regime attribution (why those streaks happen)**  
We compared entry‑time features for **normal regime** (prev_loss_streak ≤ 1) vs **loss‑streak regime** (prev_loss_streak ≥ 2).  
The loss‑streak regime shows a consistent pattern across M5 and M15:
- **Lower correlation** (`correlation_500` drops materially).
- **Lower spread volatility** (`spread_std` declines).
- **Lower vol ratio / vol regime** (`vol_ratio`, `vol_regime` fall).
- **Slightly higher beta mismatch** (hedge beta diverges from signal beta).

This indicates the guardrail is effective because it **detects persistent low‑correlation / low‑vol regimes** where the Z‑score signal loses validity.

Summary (normal → loss‑streak regime):
- **M5**: `correlation_500` 0.225 → 0.168, `spread_std` 31.4 → 29.5, `vol_regime` 1.05 → 0.98, `beta_mismatch` 0.897 → 0.922.
- **M15**: `correlation_500` 0.235 → 0.160, `spread_std` 57.7 → 50.3, `vol_regime` 1.02 → 0.97, `beta_mismatch` 0.898 → 0.937.

Files:
- `data/analysis/m5_guardrail_regime_driver_summary.csv`
- `data/analysis/m5_guardrail_regime_driver_features.csv`
- `data/analysis/m15_guardrail_regime_driver_summary.csv`
- `data/analysis/m15_guardrail_regime_driver_features.csv`

Full diagnostics:
- `data/analysis/m5_guardrail_overall.csv`
- `data/analysis/m5_guardrail_monthly.csv`
- `data/analysis/m5_guardrail_session.csv`
- `data/analysis/m5_guardrail_symbol.csv`
- `data/analysis/m15_guardrail_overall.csv`
- `data/analysis/m15_guardrail_monthly.csv`
- `data/analysis/m15_guardrail_session.csv`
- `data/analysis/m15_guardrail_symbol.csv`
- `data/analysis/m5_guardrail_effectiveness_summary.csv`
- `data/analysis/m5_guardrail_streak_stats.csv`
- `data/analysis/m5_guardrail_skip_stats.csv`
- `data/analysis/m15_guardrail_effectiveness_summary.csv`
- `data/analysis/m15_guardrail_streak_stats.csv`
- `data/analysis/m15_guardrail_skip_stats.csv`

---

## Guardrail Deep‑Dive (New)
We ran a deeper guardrail audit focused on **definition sensitivity**, **trigger stability**, and **where the losses are removed**.

**Loss definition sensitivity**
We varied the loss threshold from `pnl <= 0` to `pnl <= -2 bps`. Results are stable:
- **M5** guardrail mean stays ~15 bps (14.9–15.5), DD ~‑6.7k to ‑7.1k.
- **M15** guardrail mean stays ~31 bps (31.1–31.8), DD ~‑6.0k.

**Trigger/skip stability by year**
Guardrail skip rates are stable across years:
- **M5**: ~0.70–0.74 skip rate
- **M15**: ~0.42–0.47 skip rate

**Worst‑month attribution**
Guardrail removes the majority of losses in the worst 5% months:
- **M5**: baseline worst‑month total **‑112,404 bps**, guardrail **+24,046 bps** (≈**121%** loss removal)
- **M15**: baseline worst‑month total **‑65,878 bps**, guardrail **+355 bps** (≈**101%** loss removal)

**Concentration risk (top‑N PnL share)**
Guardrail reduces concentration materially. (Shares > 1.0 indicate other pairs are net negative.)
- **M5** baseline top‑1 share **0.62** → guardrail **0.09**
- **M5** baseline top‑3 share **0.98** → guardrail **0.25**
- **M15** baseline top‑1 share **0.26** → guardrail **0.10**
- **M15** baseline top‑3 share **0.50** → guardrail **0.28**

**Slippage sensitivity (guardrail)**
Guardrail remains positive under proportional slippage:
- **M5** mean: 15.5 → 10.9 bps at 10% slip
- **M15** mean: 31.8 → 23.7 bps at 10% slip

**Guardrail under smoothing**
Guardrail skip rates are similar under smoothing (1s/5s throttle, 0.5/1.0 bps filter):
- **M5** skip rate ~0.71–0.73
- **M15** skip rate ~0.53

**No‑leak guarantee (guardrail causality)**
The guardrail is **strictly causal**: it only observes **realized PnL at trade exit**, updates the loss‑streak **after the trade closes**, and applies cooldown **forward in time** from that exit. It does not reference any future prices, future Z‑scores, or future outcomes. Entry‑time application is explicitly avoided (and tested), so there is **no lookahead leakage** in the guardrail logic.

Files:
- `data/analysis/m5_guardrail_loss_def_sensitivity.csv`
- `data/analysis/m15_guardrail_loss_def_sensitivity.csv`
- `data/analysis/m5_guardrail_trigger_rates.csv`
- `data/analysis/m15_guardrail_trigger_rates.csv`
- `data/analysis/m5_guardrail_worst_months.csv`
- `data/analysis/m15_guardrail_worst_months.csv`
- `data/analysis/m5_guardrail_concentration.csv`
- `data/analysis/m15_guardrail_concentration.csv`
- `data/analysis/m5_guardrail_slippage_sensitivity.csv`
- `data/analysis/m15_guardrail_slippage_sensitivity.csv`
- `data/analysis/m5_guardrail_smoothing_skiprate.csv`
- `data/analysis/m15_guardrail_smoothing_skiprate.csv`

---

## Institutional Context (Why This Can Still Work)
It is reasonable to expect fragility. The guardrail’s effectiveness is not “free alpha”; it is a **risk‑control** that removes regimes where the signal becomes structurally negative.

**Why it can be effective**
- **Losses cluster**: We measured conditional expectancy collapsing after 1–2 losses. The guardrail disables trading in those regimes.
- **Regime filtering without hand‑tuned thresholds**: It uses realized outcomes rather than a fixed vol/corr cut‑off.
- **Causal and low‑latency requirement**: It does not depend on micro‑timing or order‑book effects.

**Why institutions use related ideas**
Institutions typically implement the same concept as:
- **Kill‑switches** tied to loss‑streaks or drawdown limits.
- **Regime filters** based on volatility, dispersion, or correlation.
- **Risk‑budget throttles** that reduce exposure after adverse sequences.

**Why this might work better at retail scale**
- **Low market impact**: small size avoids self‑induced slippage.
- **Simpler execution requirements**: the guardrail is robust to modest slippage and smoothing.
- **Focused universe**: fewer strategies reduce interference and make a simple risk filter effective.

**Why it could still fail**
- Structural regime change (e.g., persistent low‑corr environment).
- Broker feed quality or execution changes.
- Over‑reliance on a small subset of symbols (mitigated by guardrail, but not eliminated).

Bottom line: the guardrail is a **robust risk‑control**, not a free edge. It is consistent with institutional risk practice, and its effectiveness at retail scale is plausible—but still requires ongoing monitoring.

---

## Full‑Parameter WFO (M15 MOM)
We ran **rolling WFO** across 4 folds (train 4 years → test next year), sweeping:
- Z entry (`1.5, 2.0, 2.5`)
- Z stop (`3.0, 3.5, 4.0`)
- Z lookback (`250, 500, 750`)
- Guardrail loss streak (`3, 4, 5`)
- Guardrail cooldown (`7, 14, 21 days`)

**Best parameters were identical across all folds**:
`z_entry=1.5`, `z_stop=4.0`, `z_lookback=750`, `loss_streak=3`, `cooldown=7d`.

Per‑fold out‑of‑sample (test year) performance:
- 2022: mean 57.94 bps, max DD ‑5,333, sharpe_trade 21.82
- 2023: mean 49.50 bps, max DD ‑6,008, sharpe_trade 19.44
- 2024: mean 41.25 bps, max DD ‑3,937, sharpe_trade 19.70
- 2025: mean 40.93 bps, max DD ‑4,295, sharpe_trade 15.99

Files:
- `data/analysis/m15_mom_full_wfo_grid.csv`
- `data/analysis/m15_mom_full_wfo_best_folds.csv`
- `data/analysis/m15_mom_full_wfo_param_summary.csv`
- `data/analysis/m15_mom_best_param_trades_guardrail.csv`

## Full‑Parameter WFO (M5 MOM)
We ran the same WFO sweep on M5 (train 4 years → test next year).

**Best parameters were identical across all folds**:
`z_entry=1.5`, `z_stop=4.0`, `z_lookback=750`, `loss_streak=3`, `cooldown=7d`.

Per‑fold out‑of‑sample (test year) performance:
- 2022: mean 28.33 bps, max DD ‑3,536, sharpe_trade 22.67
- 2023: mean 28.46 bps, max DD ‑3,036, sharpe_trade 27.77
- 2024: mean 19.59 bps, max DD ‑2,831, sharpe_trade 21.02
- 2025: mean 26.01 bps, max DD ‑2,130, sharpe_trade 23.95

Files:
- `data/analysis/m5_mom_full_wfo_grid.csv`
- `data/analysis/m5_mom_full_wfo_best_folds.csv`
- `data/analysis/m5_mom_full_wfo_param_summary.csv`
- `data/analysis/m5_mom_best_param_trades_guardrail.csv`

---

## Robustness Tests (M15, WFO Parameters)
These are additional “no stone unturned” tests using the WFO‑recommended M15 parameters.

**5) Universe drift (randomly drop pairs)**  
Dropping 10–40% of pairs reduces sharpe_trade gradually but keeps mean PnL stable.
- Drop 10%: mean ~44.6 bps, sharpe_trade ~18.7
- Drop 20%: mean ~45.6 bps, sharpe_trade ~17.9
- Drop 30%: mean ~45.5 bps, sharpe_trade ~16.7
- Drop 40%: mean ~45.0 bps, sharpe_trade ~15.9

**6) Parameter stability**  
Performance degrades smoothly as we move away from best parameters (no knife‑edge).  
Median test sharpe_trade by distance from best:
- Distance ≤1: ~16.3
- Distance ≤2: ~14.6
- Distance ≤3: ~11.7

**7) Session robustness**  
All sessions remain positive; New York is weakest but still positive.
- Asia: mean ~50.1 bps
- London: ~43.5 bps
- New York: ~39.4 bps
- Late: ~46.9 bps

**8) Tail‑risk concentration**  
Removing worst months marginally improves Sharpe, but **max DD remains ~‑6,087 bps**.  
Removing worst pairs reduces Sharpe and can worsen DD.
Conclusion: DD is **not concentrated** in a tiny subset of pairs/months.

Files:
- `data/analysis/m15_universe_drift.csv`
- `data/analysis/m15_param_stability.csv`
- `data/analysis/m15_session_robustness.csv`
- `data/analysis/m15_tail_risk_concentration.csv`

## Robustness Tests (M5, WFO Parameters)
These are the same tests for M5.

**5) Universe drift (randomly drop pairs)**  
Sharpe_trade declines gradually, mean PnL stable.
- Drop 10%: mean ~24.2 bps, sharpe_trade ~21.45
- Drop 20%: mean ~24.7 bps, sharpe_trade ~20.39
- Drop 30%: mean ~24.9 bps, sharpe_trade ~19.00
- Drop 40%: mean ~24.5 bps, sharpe_trade ~17.87

**6) Parameter stability**  
Median test sharpe_trade by distance from best:
- Distance ≤1: ~20.95
- Distance ≤2: ~17.50
- Distance ≤3: ~14.27

**7) Session robustness**  
All sessions positive; New York and Asia strongest.
- Asia: mean ~25.7 bps
- London: ~21.7 bps
- New York: ~24.1 bps
- Late: ~27.9 bps

**8) Tail‑risk concentration**  
Removing worst months slightly improves Sharpe; removing worst pairs reduces Sharpe and can worsen DD.
Conclusion: DD is **not concentrated** in a tiny subset of pairs/months.

Files:
- `data/analysis/m5_universe_drift.csv`
- `data/analysis/m5_param_stability.csv`
- `data/analysis/m5_session_robustness.csv`
- `data/analysis/m5_tail_risk_concentration.csv`
---

## Reproducibility
**Logic test suite**
- Run: `uv run pytest -q`
- Tests live in `tests/` and focus on the production logic: Z‑score causality, MOM exits (Z0 + stop), timeout behavior, and guardrail cooldown semantics.
  
**Logic coverage map (what is enforced)**
- **Z‑score causality**: rolling window only (no future leakage).
- **Entry gating**: `|Z| >= threshold` and **min‑gap = 20 bars** enforced.
- **Active‑leg selection**: `beta < 0.98 → Y`, `beta > 1.02 → X`, neutral zone skipped.
- **Exit logic**: Z‑cross to 0 (loss) and Z‑stop (win), timeout at `entry+499`.
- **Guardrail semantics**: loss streak counts `pnl <= 0` as loss, cooldown by **exit time**, and pause after 3 losses.
- **End‑to‑end**: synthetic flows for M5/M15 confirm guardrail triggers and win/loss signs.

**Test matrix (logic → test file)**

| Logic Area | Test File |
| --- | --- |
| Z‑score causality | `tests/test_strategy_logic.py` |
| Feature causality (M5/M15) | `tests/test_feature_causality_m5_m15.py` |
| MOM exits (Z‑cross, Z‑stop), timeout | `tests/test_strategy_logic.py` |
| Guardrail cooldown + `pnl <= 0` loss | `tests/test_guardrail_semantics.py` |
| Active‑leg selection + min‑gap gating | `tests/test_entry_active_leg.py` |
| Guardrail ordering by exit time | `tests/test_guardrail_ordering.py` |
| WFO defaults present | `tests/test_defaults.py` |
| End‑to‑end guardrail (M5/M15) | `tests/test_end_to_end_production_m5.py`, `tests/test_end_to_end_production_m15.py` |
| End‑to‑end neutral‑zone + win/loss mix | `tests/test_end_to_end_additional.py` |

**Dataset builders**
- M5: `scripts/build_meta_dataset_v3_m5.py`
- M15: `scripts/build_meta_dataset_v3.py`

**Guardrail diagnostics**
- M5: `scripts/report_m5_guardrail_diagnostics.py`
- M15: `scripts/report_mom_guardrail_diagnostics.py` (outputs `m15_guardrail_*.csv`)

**Guardrail WFO validation**
- `scripts/wfo_mom_loss_streak.py`
- Summary: `docs/analysis/mom_loss_limiter_wfo.md`

**Full‑parameter WFO**
- `scripts/wfo_mom_full_params.py`
 - `scripts/wfo_mom_full_params_m5.py`

**Robustness suite (tests 5–8)**
- `scripts/analyze_mom_robustness_suite.py`
 - `scripts/analyze_mom_robustness_suite_m5.py`

**Guardrail effectiveness study**
- `scripts/analyze_guardrail_effectiveness.py`
 - `scripts/analyze_guardrail_regime_drivers.py`

**Guardrail plots**
- `scripts/visualization/plot_guardrail_monthly_and_dd.py`

**Integrity checks**
- `scripts/analyze_dd_timeweighted.py`
- `scripts/analyze_guardrail_entry_exit_timing.py`
- `scripts/compare_timeout_convention.py`
- `scripts/analyze_outlier_filter_with_guardrail.py`
- `scripts/analyze_pair_stability_filter.py`
- `scripts/analyze_tail_risk_guardrail.py`
- `scripts/analyze_execution_latency.py`
- `scripts/analyze_execution_latency_resim.py`
- `scripts/analyze_portfolio_constraints.py`
- `scripts/analyze_stress_tests.py`
- `scripts/analyze_tick_bar_consistency.py`

---

## Causality / Leakage Notes
- All features use only past bars at entry.
- Z‑score windows are rolling and causal (no forward data).
- Labels use future paths for evaluation only (as intended).

---

## Feature Dictionary (Kalman Scout)
These are the causal features used in dataset construction, even though inference is now rule‑based. Units in bps where noted.

Categorical features:
- `active_leg`: which leg is traded (X or Y).
- `side`: sign of Z at entry (LONG if Z>0, SHORT if Z<0).

Signal quality and lags:
- `z_entry`: Z‑score at entry.
- `z_velocity`: Z change vs 5 bars ago.
- `z_lag1`, `z_lag2`, `z_lag3`: Z at prior bars.
- `dz_lag1`, `dz_lag2`: short‑term slope proxies.
- `spread_std`: std of spread error over 500 bars (bps).

Beta and hedge context:
- `beta`: current Kalman beta.
- `beta_lag1`, `beta_lag2`: prior betas.
- `beta_stability`: beta std over 100 bars.
- `signal_beta_lookback`: mean beta over 500 bars.
- `hedge_beta_lookback`: mean return‑beta over 500 bars.
- `beta_mismatch`: clipped ratio `hedge_beta_lookback / signal_beta_lookback`.

Regime and correlation:
- `vol_ratio`: std(diff(Y)) / std(diff(X)) over 500 bars.
- `correlation_500`: corr(X,Y) over 500 bars.
- `trend_strength`: 100‑bar spread slope / spread std.

Time context:
- `hour`: entry hour (UTC).
- `day_of_week`: entry weekday.

Return and ATR context:
- `ret_X_16b`, `ret_Y_16b`: 16‑bar returns.
- `ret_X_1h`, `ret_Y_1h`: 1‑hour proxy returns.
- `atr_ratio`: 4‑bar range ratio (Y/X) over 100 bars.
- `entry_atr`: 50‑bar return std (bps).
- `vol_regime`: short/long volatility ratio (50/500).

---

## Deprecated / Not Used
- ML models are **not used**.
- Edge score thresholds are **not used**.
- REV strategy is **not traded**.
