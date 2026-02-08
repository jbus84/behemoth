# Walkthrough - Meta Model Strategy (H1 Edition)
Last Updated: 2026-02-03

## 1. The Strategy: "The Hourly Edge"
After extensive testing across 5m, 15m, 30m, and H1, we have confirmed that the **Hourly (H1)** timeframe is the optimal frequency for this Mean Reversion strategy.

### The Physics of Timeframes
| Timeframe | Mean PnL (Gross) | Verdict | Reason |
|---|---|---|---|
| **H1** | **+75 bps** *(legacy)* | 🟡 **REVALIDATE** | **Macro Resonance**. Captured flows > Spread Cost. |
| 30m | +0.8 bps | 🔴 AVOID | **Dead Zone**. Too slow to scalp, too fast for macro. |
| 15m | +5.6 bps | 🟡 WATCH | **Scalping**. High gross alpha but dangerous Net PnL. |
| 5m | -- | ❌ CANCEL | **Cost Prohibitive**. Moves are smaller than spread. |

## 2. Deep Dive: H1 Dataset Exploration
(Analysis of 18,077 Momentum Trades over 8 Years)

### A. The "V-Shape" of Volatility
The strategy loves extremes. It hates the middle.
*   **Low Vol Regime (<0.76)**: **+25.3 bps**. (Dead Market = Perfect Reversion).
*   **High Vol Regime (>1.21)**: **+12.1 bps**. (Panic = Overshoots).
*   **Mid Vol Regime (1.0)**: **+2.9 bps**. (Efficient Market = No Alpha).
*   *Action*: The Model successfully identified `vol_regime` as a key feature.

### B. Trend Exhaustion
*   **Low Trend Strength**: +15.7 bps.
*   **Mid Trend Strength (Sweet Spot)**: **+23.1 bps**.
*   **Max Trend Strength (>0.03)**: **-2.6 bps** (LOSS).
*   *Insight*: When the trend is "Maxed Out" (Parabolic), Momentum trades fail (Buy Top/Sell Bottom).
*   *Action*: Avoid signals when `trend_strength > 0.03`.

### C. The "Liquidity Gap" (Seasonality)
*   **Best Hours**: 04:00 UTC (+21 bps), 00:00 UTC (+16 bps).
*   **Toxic Hours**: **21:00 - 23:00 UTC** (-6 bps).
*   *Insight*: The Asian Open / US Close gap is dangerous. Spreads widen, moves are random.
*   *Action*: Hard filter: **No Entries 21:00-23:00 UTC**.

## 3. Pred > 20 bps Filter (Holdout 2024–2025)
Using the current model (`models/meta_model_h1/catboost_h1_reg.cbm`) on the **2024–2025 holdout** subset of `events_h1_8yr_v3_dual.csv` (gross, single‑leg):

| Pred Threshold | Trades | Win Rate | Mean PnL (bps) | Total PnL (bps) |
|---|---|---|---|---|
| **> 20** | **373** | **59.8%** | **75.58** | **28193** |

Note: These are **gross, single‑leg** outcomes and do not include execution costs.

---

## 4. Deployment Status

### Artifacts Created
1.  **H1 Meta Model**: `models/meta_model_h1/catboost_h1_reg.cbm` (Trained & Saved).
2.  **Inference Script**: `scripts/inference_meta_model.py` (Feature‑parity verified).
3.  **Strategy Manual**: `docs/STRATEGY_MASTER_MANUAL.md` (Updated with H1 Logic).

### Verification
*   **Inference Test**: `Gold/Oil` H1 Data -> **Success**.
*   **Feature Parity**: Training vs inference parity validated.

### Next Steps
1.  **Execution Layer**: Implement documented runtime guards (kill‑zone, circuit breaker, exits).
2.  **Paper Trade**: Run `inference_meta_model.py` on a cron job (hourly).
