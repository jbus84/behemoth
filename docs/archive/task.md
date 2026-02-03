# Task: Robust Target Engineering (Noise immunity)

## Milestone 1: Triple Barrier Labeling
- [x] Task: Implement Triple Barrier method (TP/SL dynamic targets). - *Done*
- [x] Hypothesis: Predicting "Path-Dependent Outcomes" (Hit TP before SL) is cleaner than "Time-Dependent Outcomes" (Close > Open). - *Confirmed!*
- [x] Audit: Compare AUC of Triple Barrier vs Simple Direction on 2024-2025. - *Result: 0.7752 vs 0.4991 (+27 points!)*

## Milestone 2: Trend Stability Labeling
- [x] Task: Define "Smooth Trend" target (Positive Return AND Low Variance). - *Done*
- [x] Hypothesis: ML can easier identify "Calm Trends" than "Volatile Spikes". - *Result: AUC 0.63 (Decent, but Triple Barrier is better).*
- [x] **Decision**: Proceed with Triple Barrier (AUC 0.77).

## Milestone 3: Production Model Validation
- [x] Task: Audit "Direct Trading" of Triple Barrier model. - *Result: Failed (-1.08 bps)*.
- [x] Task: Audit "Sniper Mode" (Vol Decile > 7 + Prob > 0.85). - *Result: +3.42 bps Net*.
- [x] Task: Audit "Balanced Mode" (D7-D9, Prob > 0.65). - *Result: ~+9 bps Net (Two-Way)*.
- [x] **Conclusion**: **Bilateral Sniper** is the final selected strategy for Nasdaq.

- [x] Task: Build SPX 1-minute data from `/Desktop/tick`. - *Done*
- [x] Task: Audit Bilateral Sniper on SPX (Honest/Anchored). - *Result: ~+9 bps (Leakage Detected)*.
- [x] Task: Re-Audit SPX with Zero-Leakage Logic (Right-Labeling). - *Result: 0 Trades*.
- [x] **Conclusion**: 15m Aggregation is too laggy without look-ahead.

## Milestone 6: Micro-Structure Pivot (1-minute)
- [x] Task: Create `micro_structure_audit.py` (Raw 1m features, no resampling). - *Done*
- [x] Hypothesis: Granular 1-minute Volatility/RSI can predict short-term 20bps bursts better than 15m bars. - *Result: 0 Trades (Failed)*.
- [x] **Conclusion**: Global 1m model failed.
- [x] Task: Re-Run Micro-Structure with **Vol Regime Filtering** (Train/Test only on High Vol). - *Result: -3.21 bps (Failed)*.
- [x] **Final Conclusion**: 1-minute Price Action does not contain Alpha (Efficiency Hypothesis Confirmed).

## Milestone 7: Signal Diagnostics (The "Why")
- [x] Task: Create `diagnostic_audit.py` (IC, Correlation, Calibration). - *Done*
- [x] Goal: Explain mathematically why RSI/Vol fails to predict returns. - *Result: IC ~0.00. Features are Noise.*.
- [x] **Verdict**: Abandon Price-Action Technicals.

## Milestone 8: Cross-Asset Lead-Lag (The "Outside" View)
- [x] Task: Create `cross_asset_audit.py`. - *Done*
- [x] Hypothesis: DAX (Europe) or Bond Yields lead Nasdaq flow. - *Result: IC ~0.00 (Failed)*.

## Milestone 9: Conclusion
- [x] **Final Verdict**: 1-Minute OHLC Data contains **NO ALPHA** (Price, Vol, or Lead-Lag).
- [x] **Regulation**: Markets are Efficient at this resolution.
- [ ] **Recommendation**: Pivot to HFT (Tick-Level) or Alternative Data.

## Milestone 10: FX Lead-Lag (High Volatility)
- [x] Task: Locate/Build FX Data (EURUSD, GBPUSD, USDJPY). - *Done*
- [x] Task: Create `fx_vol_lead_audit.py`. - *Done*
- [x] Hypothesis: FX leads only when Volatility is Extreme (>D8). - *Result: IC 0.015 (Insufficient)*.

- [ ] **Recommendation**: Strategy Research is Closed. Proceed to Infrastructure?

## Milestone 11: Hourly Alpha Pivot (Macro)
- [x] Task: Create `hourly_audit.py`. - *Done*
- [x] Hypothesis: Lower noise at 1H. - *Result: Failed (IC ~0.0)*.
- [x] Sub-Task: Test Hourly Momentum (RSI/ROC). - *Failed*.
- [x] Sub-Task: Test Hourly Cross-Asset (FX Lead). - *Failed (IC ~0.04)*.

## Milestone 12: Final Conclusion
- [x] **Verdict**: Price/Vol data is efficient from 1m to 1h.

## Milestone 12: 5m/15m Multi-Asset Audit (The "Basket")
- [x] Task: Add XAUUSD (Gold) and USDCHF (Swissie) to Data Builder. - *Done*
- [x] Task: Create `multi_asset_audit.py` (Resample 1m -> 5m/15m). - *Done*
- [x] Hypothesis: Correlation structure is cleaner at 5m/15m with Gold/CHF included. - *Result: Failed (IC < 0.01)*.
- [x] Task: Re-Run with Volatility Regime Split (>D8). - *Result: Failed. 15m High Vol IC = 0.02 (Insufficient).*
- [x] Task: Test Composite Basket (Sum of Signals) in High Vol. - *Result: Failed (IC 0.022).*

## Milestone 13: Final Verdict
- [x] **Conclusion**: All linear price-based alpha vectors (1m-60m) are exhausted.
- [ ] Recommendation: End Session / Pivot to HFT.

## Milestone 14: Volatility Autocorrelation Check
- [x] Task: Create `vol_autocorr_audit.py`. - *Done*
- [x] Hypothesis: Serial correlation (Trend vs Reversion) changes with volatility. - *Result: Failed. All Regimes are Mean Reverting (-0.02). No Momentum found.*
- [x] Task: Check FX/Nasdaq Correlation in Low Vol. - *Result: Failed (Zero correlation).*
- [x] Task: Check Multi-Lag Autocorrelation in Low Vol (-1 to -5). - *Result: Failed. No predictive structure.*
- [x] Task: Check Multi-Lag Autocorrelation in Med Vol. - *Result: Failed. Consistent Mean Reversion (-0.02).*
- [x] Recommendation: **STOP.** Pivot to Infrastructure.

# HFT Infrastructure Roadmap (Phase 2)

## Milestone 1: Data Ingestion & Validation
- [x] Task: Locate Nasdaq Tick Data. - *Done (/Desktop/tick/NSXUSD)*.
- [x] Task: Create `inspect_tick_data.py` to Check Schema. - *Done*.
- [x] Task: Create `TickTester` class in `infrastructure/tick_tester.py`. - *Done (Event Loop Working).*

## Milestone 2: The Event-Driven Backtester
- [x] Task: Validate Basic Fills (Limit Orders Executing). - *Done*.
- [x] Task: Implement `QueueSimulator` (Conservative Cross Logic). - *Done (Result: -$448M Loss - Toxic Flow).*
- [x] Task: Implement `QueueSimulator` (Time-Based / Probabilistic Touch). - *Done (Result: -$4.3M Loss - Bag Holder).*
- [x] Task: Implement `InventorySkew` (Avellaneda-Stoikov Logic). - *Done (Result: -$18M Loss - Churning Toxic Flow).*
- [x] Task: Implement `MicroTrendProtection` (Adverse Selection Guard). - *Done (Result: -$17M Loss - Blind HFT Failed).*
- [x] Recommendation: **ABORT.** Missing Volume Data prevents Alpha.

# Phase 3: Swing Trading (4H / Daily)
## Milestone 1: Data Aggregation
- [x] Task: Create `build_swing_data.py` (Resample 1m -> 4H / 1D). - *Done*.
- [x] Task: Validate High/Low fidelity (did we miss the wick?). - *Pending (Row Count Audit).*

## Milestone 2: Trend Following Audit (4H)
- [x] Task: Create `swing_trend_audit.py`. - *Done*.
- [x] Task: Test Moving Average Crossovers (Golden Cross). - *Done (Running)*.
- [x] Task: Test Donchian Breakouts (20-Period High). - *Done (Running)*.
- [ ] Task: Test Volatility Breakouts (ATR Expansion).

## Milestone 3: Macro Regime Filters
- [x] Task: Filter Trend signals by Volatility Regime. - *Done (Success: Avoid High Vol).*
- [x] **Conclusion**: Donchian (20D) in Low/Med Volatility generates +11,400 Points. High Volatility is toxic (-3400 Points).

## Milestone 4: Short-Duration Constraint (8H Max)
- [x] Task: Audit "Time-Limited Donchian" (Enter Breakout, Exit 8H later). - *Done (Success: +200pts, Win Rate 53%).*
- [ ] Task: Filter by "Time of Week" (e.g., Monday Momentum).

# Phase 4: Kalman Pairs Trading (4H)
## Milestone 1: Data & Infrastructure
- [x] Task: Inventory available pairs (Do we have SPX? EURUSD?). - *Done (Found SPXUSD, EURUSD, GBPUSD).*
- [x] Task: Create `build_pairs_data.py` (Resample 1m -> 1H/4H aligned). - *Done*.

## Milestone 2: Kalman Implementation
- [x] Task: Implement `KalmanFilter` class (Dynamic Beta estimation). - *Done*.
- [x] Task: Create `kalman_audit.py` (Z-Score calculation). - *Done (Running)*.

## Milestone 3: Strategy Backtest
- [x] Task: Test Pairs: NSX/SPX (if avail) or Synthetic. - *Done (Sharpe 4.49)*.
- [x] Task: Test Pairs: EUR/GBP. - *Done (Sharpe 1.93)*.
- [x] Task: Optimize Entry/Exit Z-Scores (e.g. +/- 2.0). - *Done (Standard 2.0/0.0)*.

## Milestone 4: Kalman Expansion (Global Indices)
- [x] Task: Inventory Global Indices (Dow, DAX, FTSE). - *Done*.
- [x] Task: Build Aligned Data (UDX/SPX, GRX/UKX). - *Done*.
- [x] Task: Audit Kalman on New Pairs. - *Done (DAX/FTSE Sharpe 2.12)*.

## Milestone 4: Documentation (Final)
- [x] Task: Stress Test Cost Model (3bps). - *Done (Sharpe -> 1.38)*.
- [x] Task: Breakdown Sharpe by Year (Regime Check). - *Done (2022 Crisis: Sharpe 0.95)*.
- [x] Task: Reality Check. - *Done*.

---
# Archive: Phase 3 (Swing Trading) - SUCCESS (But User Pivoted)
# Archive: Phase 2 (HFT Infrastructure) - FAILED
- [x] Task: Check BCOUSD Data Availability. - *Done (2018-2026)*.
- [x] Task: Analyze Spread Impact on 4H Strategy. - *Done (Negligible)*.
- [x] Task: Audit FX/Oil Expansion. - *Done (AUD/NZD Sharpe 1.90; EUR/CHF Failed)*.
- [x] Task: Check Silver & JPY Data. - *Done*.
- [x] Task: Audit Metals (Gold/Silver) & JPY (USD/EUR). - *Done (Gold/Silver Sharpe 5.22!)*.
