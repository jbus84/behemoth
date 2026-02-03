# Institutional Audit Report: Kalman Pairs Strategy

## 1. Executive Summary & Verdict
**Status**: 🔴 **DEBUNKED / DO NOT DEPLOY**
**Final Verdict**: The strategy's "High Sharpe" is a statistical illusion caused by **Under-Hedging**.

While the strategy appears to have a Sharpe Ratio of 9.88 on paper, an Institutional Backtest reveals that capturing this alpha requires taking massive, unhedged directional risk. When properly hedged, the alpha disappears.

---

## 2. The "Beta Mismatch" Trap

The core failure mechanism is a discrepancy between the **Signal Beta** and the **Risk Beta**.

### A. The Signal (The Illusion)
*   The Kalman Filter regresses `Log(Silver)` vs `Log(Gold)`.
*   Because Gold prices (~1300) are higher than Silver (~17), the regression slope (Beta) is crushed to **~0.4**.
*   **Observation**: The spread `Silver - 0.4 * Gold` is perfectly Mean Reverting (Stationary).
*   **Temptation**: Verify this spread, see High Sharpe, and trade it.

### B. The Risk (The Reality)
*   Silver is **1.41x** more volatile than Gold (empirically calculated on returns).
*   To be **Market Neutral** (safe), for every $1 of Silver you simply MUST hold **$1.41** of Gold.
*   **The Trap**: The strategy signals to hold only **$0.40** of Gold (based on the Signal Beta).
*   **Net Exposure**: You are **Under-Hedged** by ~70%.
    *   You think you are trading a spread.
    *   In reality, you are **Long Silver / Short Gold** with a massive net long exposure to Silver's volatility.

### C. The Consequence
*   **In Backtest**: The "margin calls" occurred because when Silver trended, the $0.40 Gold hedge was insufficient to offset the $1.00 Silver loss.
*   **The "Alpha"**: The 76bps profit per trade is simply the **Risk Premium** for holding this unhedged volatility. It is not arbitrage.

---

## 3. Statistical Proof

We ran two definitive tests:

| Portfolio | Beta | Stationarity (ADF) | Risk Profile | Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **Signal Portfolio** | 0.41 | ✅ **Pass** (p < 0.05) | ⚠️ **Dangerous** | Mean Reverting but blows up account. |
| **Hedged Portfolio** | 1.41 | ❌ **Fail** (p = 0.33) | 🛡️ **Safe** | Risk Neutral but acts as Random Walk (No Profit). |

**Conclusion**: You cannot have both.
*   If you hedge (Beta 1.41), you lose the mean reversion.
*   If you chase mean reversion (Beta 0.41), you lose the hedge.

---

## 4. Final Recommendation

**DO NOT DEPLOY** this strategy in its current form.
To make this viable, you would need to:
1.  Accept that it is a **Directional Volatility Strategy**, not an Arbitrage.
2.  Reduce leverage to **1:1** (Cash Only).
3.  Treat it as a "Smart Beta" index, not a HFT Alpha.

For an HFT/Prop Trading desk, this strategy is **REJECTED**.

---
*Audit Completed by Antigravity Agent on 2026-02-02.*
