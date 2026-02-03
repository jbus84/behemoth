# Debunk: STRATEGY_MASTER_MANUAL.md

Date: 2026-02-03
Scope: `docs/STRATEGY_MASTER_MANUAL.md` only (non-archive). Repo review includes `scripts/`, `data/meta_model/events_h1_8yr_v3_dual.csv`, and model artifacts.

## Executive Summary
The manual makes strong claims about market-neutrality, net expectancy, and production readiness that are not supported by the current code or datasets. The most material issues are:

1. The training and simulation for the meta model are not market-neutral pairs trades. They trade a single “active leg,” so PnL is directional, not spread-based. This contradicts the manual’s core premise.
2. The “+75 bps per trade, post-commission” claim is not reproduced by the H1 meta dataset. The dataset’s MOM mean is ~12 bps gross, REV is ~-12 bps, and overall mean is 0 by construction. Costs are not deducted anywhere in the meta dataset pipeline.
3. Inference is materially mismatched to training. `trend_strength` is never computed, `atr_ratio` is hard-coded to `1.0`, and several filters claimed in the manual are not implemented. This makes “Production Ready” and “Verified Live Ready” unsubstantiated.

## Evidence And Claim-by-Claim Findings

### Claim: Market-neutral, spread-based strategy
Manual statement: “We trade synthetic spreads… market neutral.”

Evidence: `scripts/build_meta_dataset_v3_h1.py` simulates trades on **one leg only** via `simulate_trade()` and `prices = y if active_asset == 'Y' else x`. PnL is computed from that single leg’s log price movement, not from the spread or a hedged pair.

Impact: The meta model is trained on directional single-leg returns. This is not market-neutral and invalidates the manual’s description of the strategy’s core risk profile.

### Claim: Net expectancy +75 bps per trade (post-commission)
Manual statement: “Net Expectancy: +75 bps per trade (Post-Commission).”

Evidence: `data/meta_model/events_h1_8yr_v3_dual.csv` is produced by `scripts/build_meta_dataset_v3_h1.py` and contains no cost deduction. `cost_y`/`cost_x` are never applied to `pnl_bps`. Direct inspection of the CSV shows:

- Total events: 36,154
- MOM mean: +12.26 bps (gross)
- REV mean: -12.26 bps (gross)
- Overall mean: 0.00 bps (gross)

Impact: The +75 bps net claim is not supported by the training dataset and appears inconsistent with the actual data used to train the model.

### Claim: 2025 Grand Scan results (pair win rates and mean net PnL)
Manual table: Gold/Oil 63% win rate, +79 bps mean net PnL; CAC/NZD 59% and +76 bps; Oil/Silver 58% and +43 bps; CAC/AUDCAD 57% and +60 bps.

Evidence from `events_h1_8yr_v3_dual.csv` (gross, single-leg):

- Gold/Oil: MOM mean +9.28 bps, win rate 43.5%; REV mean -9.28 bps, win rate 56.5%.
- CAC/NZD: MOM mean +29.51 bps, win rate 45.8%; REV mean -29.51 bps, win rate 54.2%.
- Oil/Silver: MOM mean -8.58 bps, win rate 40.8%; REV mean +8.58 bps, win rate 59.2%.
- CAC/AUDCAD does not appear in the H1 meta dataset.

Impact: The table in the manual is not reproduced by the H1 meta dataset, and at least one listed pair is missing from the meta training data. The reported “Mean Net PnL” appears to be from a different methodology or is inflated.

### Claim: Two-stage decision engine with regime features
Manual statement: “CatBoost regressor trained on 8 years of H1 data; uses volatility, beta stability, trend strength; execute if predicted PnL > 20 bps.”

Evidence: Training uses `scripts/train_meta_model_h1.py` and `data/meta_model/events_h1_8yr_v3_dual.csv`. However, `scripts/inference_meta_model.py` does not compute `trend_strength` at all, and `atr_ratio` is set to `1.0` for all rows. The inference script also omits the manual’s volatility gate (`Volatility > 2.5`), the UTC kill-zone filter, and the circuit breaker.

Impact: Inference inputs do not match the training feature set. This creates a distribution shift and likely causes errors or degraded predictions. Claimed live readiness is not credible without feature parity and the missing filters.

### Claim: Entry/Exit rules and risk controls
Manual statements include:
- Entry requires `|Z| > 1.5` and “Volatility > 2.5 annualized.”
- Exit on Z-score return to 0 or model flip.
- Stop loss if Z-score > 3.5.
- Circuit breaker after 3 consecutive losses; pause 30 days.
- No entries 21:00–23:00 UTC.

Evidence: `scripts/inference_meta_model.py` only gates on `|Z| > 1.5` and `pred_pnl > 20 bps`. None of the volatility, kill-zone, circuit breaker, or stop-loss logic appears in inference. `simulate_trade()` in `scripts/build_meta_dataset_v3_h1.py` uses Z-based exits but not the 72-hour time stop or circuit breaker.

Impact: The deployed behavior does not match the manual’s risk controls. Live outcomes would deviate materially from documented expectations.

### Claim: Centered Kalman filter is the core innovation
Manual statement: Rolling mean centering removes intercept and yields a true volatility ratio beta.

Evidence: Some scripts do use centered inputs (`scripts/build_meta_dataset_v3_h1.py`, `scripts/scan_full_universe_h1.py`). Others do not (`scripts/monitor_pairs.py`, `scripts/analyze_h1_metrics.py`). The dashboard shown in README uses uncentered logic and 4H data, not the H1 centered logic described in the manual.

Impact: Reported metrics and live monitoring are not aligned with the “centered Kalman” design. The manual mixes results from inconsistent implementations.

### Claim: Holding period ~6 days
Manual statement: “Holding period is ~6 days.”

Evidence: The H1 meta dataset has mean duration of ~150.6 bars, which is ~6.25 days. This is consistent **within the single-leg simulation** used to build the dataset.

Impact: This claim is supported by the dataset, but only for the single-leg simulation, not a true market-neutral spread trade with costs.

### Claim: “Production Ready / Verified Live Ready”
Manual and walkthrough state the system is deployable and verified.

Evidence: `scripts/inference_meta_model.py` is missing features (`trend_strength`) and uses placeholder values (`atr_ratio`). It also lacks multiple risk controls described in the manual. This would either crash or produce materially different inputs than training.

Impact: The live system, as written, is not production safe. At minimum it is unverified against the documented strategy.

## Repro Notes (Local)
These metrics were derived with a pure-Python CSV pass over `data/meta_model/events_h1_8yr_v3_dual.csv` (no external libs). You can reproduce with a short script; the key values are listed above.

## What Would Be Needed To Validate The Manual
1. A true spread-based backtest (two-leg PnL with beta hedging) that matches the manual’s rules, including costs from tick-derived spreads.
2. A full feature-parity inference pipeline matching training (trend_strength, atr_ratio, vol_regime, etc.).
3. Explicit tests showing the risk controls (kill zone, stop, circuit breaker) are enforced in live inference and in backtests.
4. A documented, reproducible audit for the “Grand Scan” table with source data and parameters.

## Bottom Line
As implemented, the strategy is **not** the market-neutral, centered-Kalman, cost-aware system described in `docs/STRATEGY_MASTER_MANUAL.md`. The primary dataset for the meta model is single-leg, cost-free, and symmetric across MOM/REV, making the reported net expectancy and pair rankings unsubstantiated. The inference engine also diverges materially from training, undermining any claim of production readiness.
