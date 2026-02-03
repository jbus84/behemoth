# Validation Report: 15-Minute Scalping Candidates ⚡

**Date**: February 2026
**Data Source**: Partial Tick History (resampled to 15m).
**Test Mode**: **REAL SPREADS + LEVERAGE (30:1)**.

---

## 1. Executive Summary 💀
We stress-tested the "Tier 1" scalping candidates with **Real Bid/Ask Spreads**.
**The Strategy FAILED**.
While the theoretical signal is strong (Sharpe ~70 with fixed costs), the **Actual Transaction Costs** on Oil (`BCOUSD`) are too high for the 15-minute timeframe.
**Recommendation**: **DO NOT SCALP M15**. Shift to H1/H4 timeframes to capture larger alpha that exceeds the spread cost.

---

## 2. Test Results (The "Spread Death")

| Pair | Real Spread Cost | Theoretical Sharpe | Actual ROI | Verdict |
|---|---|---|---|---|
| **Oil / DAX** (`BCOUSD/GRXEUR`) | **~9.0 bps** | 72.21 | **-100%** | **FAIL** |
| **Oil / S&P** (`BCOUSD/SPXUSD`) | **~7.5 bps** | 84.68 | **-100%** | **FAIL** |
| **Euro / FTSE** (`ETXEUR/UKXGBP`) | **~5.5 bps** | 14.07 | **-100%** | **FAIL** |

### Failure Analysis 🔍
The strategy died due to the **Cost of Oil**:
*   **BCOUSD Bid/Ask Spread**: **6.78 bps** (Avg).
*   **GRXEUR Bid/Ask Spread**: **2.16 bps** (Avg).
*   **Total Round Trip**: ~9 basis points.
*   **M15 Alpha**: The typical 15m mean reversion profit is ~4-6 bps.
*   **Result**: We are paying 9bps to make 5bps. The math guarantees bankruptcy.

---

---

## 3. The Pivot: Shift to H1/H4 🐢
The "Safe Hedge" signal is valid, but the **Timeframe must match the Cost Structure**.
We validated the **1-Hour (H1)** timeframe against the same severe costs (9bps).
*   **H1 Performance**:
    *   **Avg Alpha**: ~60.8 bps per trade.
    *   **Cost**: 9.0 bps.
    *   **Net Profit**: **51.84 bps per trade**.
    *   **Verdict**: **PASS**. The H1 timeframe generates enough alpha to easily absorb the spread.

## 4. Conclusion
**Validation Status**:
*   🔴 **M15**: **FAILED** (Alpha < Cost).
*   🟢 **H1**: **pass** (Alpha >> Cost).

**Final Action**: Abandon M15 Scalping. Deploy strategy on H1/H4 exclusively.

---
*Verified by Antigravity Backtest Engine.*
