
# ⚡ M15 FX Execution Cheat Sheet (EUR/USD vs GBP/USD)

**Date**: Feb 2026
**Valid For**: 2025 Regime (High Volatility / Crisis).
**Warning**: Fails in Low Volatility Regimes (2018-2024).

---

## 1. The Setup (Common)
*   **Predictor (X)**: `EURUSD`
*   **Target (Y)**: `GBPUSD`
*   **Indicator**: Kalman Filter Z-Score of the pair `GBP = alpha + beta * EUR`.

---

## 2. Option A: The "Anchor" (Mean Reversion) ⚓
**Trade**: `EURUSD` Only.
**Logic**: EUR acts as the anchor. When the spread widens, EUR moves to close the gap.

*   **Trigger**: Z-Score $>$ **2.0** (GBP Expensive / EUR Cheap).
*   **Action**: **BUY EURUSD**.
*   **Target**: Z-Score crosses **0.0** (Gap Closed).
*   **Stop Loss**: Z-Score $>$ **3.5** (Regime Break).
*   **Sizing**: Standard Unit (e.g., 1 Lot).

---

## 3. Option B: The "Rocket" (Momentum) 🚀
**Trade**: `GBPUSD` Only.
**Logic**: GBP acts as the driver. When the spread widens, GBP is breaking out. It will NOT come back.

*   **Trigger**: Z-Score $>$ **2.0** (GBP Expensive / Breakout).
*   **Action**: **BUY GBPUSD** (Bet on Continuation).
*   **Target**: Z-Score $>$ **3.5** (Trend Extension). Or trailing stop.
*   **Stop Loss**: Z-Score $<$ **0.0** (Devation Failed / Reverted).
*   **Sizing**: Standard Unit (e.g., 1 Lot).

---

## 4. The "Golden Rule" of M15 FX ⚠️
**Never confuse the legs.**
*   If you Fade GBP (Short @ Z>2), you lose (-1500 bps).
*   If you Follow EUR (Long @ Z>2), you lose (-1000 bps).

**Symmetry**:
*   Trade **EUR** against the move (Reversion).
*   Trade **GBP** with the move (Momentum).

## 5. Risk Warning
*   **Win Rate**: ~45-50%.
*   **Risk/Reward**: High (Momentum moves are large).
*   **Regime Risk**: If market goes quiet (2024 style), both strategies bleed spread costs. **Only trade when VIX > 15.**
