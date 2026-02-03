# Universal Beta Audit: Cross-Asset Validity Report

## 1. Objective
To determine if the "Beta Mismatch" (Signal vs Risk) observed in Gold/Silver is a systemic flaw across all asset classes, or if specific pairs remain viable.

## 2. Audit Methodology
For every pair, we calculated:
1.  **Signal Beta**: The regression coefficient on Price Levels (what the algorithm sees).
2.  **Hedge Beta**: The regression coefficient on Price Returns (what the risk manager sees).
3.  **Mismatch Ratio**: `Hedge / Signal`. (Target: 1.0).
4.  **Safe Stationarity**: ADF Test on the *Risk-Neutral* Spread.

## 3. Results Matrix

| Asset Class | Pair | Signal Beta | Hedge Beta | Mismatch | Safe Stationary? | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Metals** | Gold/Silver | 2.43 | 0.41 | **0.17x (Risk)** | ❌ (0.93) | **FAIL** (Toxic) |
| **Energy** | Oil/CAD | 15.25 | -1.73 | **Chaos** | ❌ (0.28) | **FAIL** (Broken) |
| **Indices** | Nasdaq/SPX | 1.14 | 1.14 | **MATCH** | ❌ (0.30) | **FAIL** (Random Walk) |
| **FX** | **AUD/NZD** | **0.83** | **0.79** | **MATCH** | ✅ **(0.01)** | **PASS** 🏆 |

## 4. Deep Dive Analysis

### A. The "Toxic" Class (Metals & Energy)
*   **Issue**: Massive discrepancy between Price Levels and Volatility.
*   **Mechanism**: The algorithm fits the Price Level ratio (~2.5 for Gold/Silver), but the Volatility ratio is totally different (~0.4).
*   **Result**: Trading the signal leaves you with unhedged directional exposure.

### B. The "Efficient" Class (Indices)
*   **Issue**: Market Efficiency.
*   **Mechanism**: Nasdaq and SPX are perfectly correlated in volatility (Beta Match), but their spread is a **Random Walk**. There is no mean reversion to capture.
*   **Result**: You don't lose money on the hedge, you just bleed slowly to spread costs.

### C. The "Golden" Class (Homogeneous FX)
*   **Survivor**: **AUD/NZD**.
*   **Why**: Both currencies are driven by similar macro factors (China growth, Commodities) and have nearly identical price levels and volatilities.
*   **Result**: Signal Beta (0.83) matches Risk Beta (0.79). The spread is truly stationary.
*   **Action**: This is the **ONLY** valid application of the Kalman Strategy.

## 5. Final Recommendation

1.  **Decommission**: Gold/Silver, crypto-commodities, and Index pairs.
2.  **Pivot**: Refocus the entire fund on **Homogeneous FX Pairs** (AUD/NZD, EUR/CHF, CAD/NOK).
3.  **Deploy**: Use the `kalman_backtest_returns_hedge.py` logic specifically optimized for AUD/NZD.

---
*Audit Completed by Antigravity Agent.*
