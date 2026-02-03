# The "Meta Model" Strategy: Master Manual 📘

> [!TIP]
> **STRATEGY STATUS: DEPLOYABLE (H1 CORE)** 🚀
> **Architecture**: "The Scout & The General"
> **Core Edge**: Quantifying the probability of Mean Reversion using Volatility Regimes.
> **Timeframe**: **Hourly (H1)**.
> **Net Expectancy**: **+75 bps per trade** (Post-Commission).

**Version**: 5.0 (The Meta Era)
**Date**: February 2026
**Status**: **PRODUCTION**

---

## 1. Executive Summary 🎯

This strategy solves the fundamental flaw of naive Mean Reversion.
Naive strategies buy every "low" price. They get crushed when the price keeps dropping (Momentum).
Our solution uses a **Two-Stage Decision Engine**:

1.  **Stage 1: The Scout (Centered Kalman Filter)**.
    *   *Role*: Precision Anomaly Detection (Signal Generation).
    *   *Mechanism*: 
        *   **Dynamic Regression**: Estimates the hedge ratio ($\beta_t$) between two assets ($Y, X$) in real-time. State-Space Model: $y_t = \beta_t x_t + \epsilon_t$.
        *   **Rolling Mean Centering**: Crucial innovation. We pre-process inputs by subtracting their 500-hour rolling mean ($y' = y - \mu_y$). This effectively removes the "Intercept" component, forcing the Beta to reflect pure **Volatility Ratio** rather than price levels, preventing leverage distortion.
        *   **Recursive Update**: At every time step $t$, the filter updates its estimate of $\beta_t$ based on the new observation, adjusting for prediction error.
    *   *Output*: **Z-Score ($z_t$)**. calculated as the normalized Spread Error over a rolling 500-hour window. A Z-Score > 1.5 indicates a **Statistically Significant Dislocation** (1.5 Standard Deviations from fair value). "The rubber band is stretched."

2.  **Stage 2: The General (Meta Model)**.
    *   *Role*: Decision Authority.
    *   *Method*: A **CatBoost Regressor** trained on 8 years of H1 data. It analyzes the *context* of the anomaly (Volatility, Beta, Trend Strength).
    *   *Output*: **Predicted PnL**. "Is this a trap or an opportunity?"
    *   *Action*: Only execute if Predicted PnL > **+20 bps**.

---

## 2. The Theory: Physics of the Spread 🧠

### A. The Signal Source (Kalman Scout)
We trade **Synthetic Spreads** between cointegrated assets (e.g., $S_t = \ln(Gold) - \beta \ln(Oil)$).
*   **Dynamic Beta**: We do not use fixed ratios. The beta ($\beta_t$) adapts every hour.
*   **Mean Centering**: We remove the interpretability issues of "Intercepts" by centering data on a 500-hour rolling mean. This isolates pure **Volatility/Slope**.

### B. The Decision Layer (Meta General)
Why do we need a Meta Model?
*   **The Problem**: A Z-Score of +2.0 in a **Low Volatility** range works perfectly (Reversion). A Z-Score of +2.0 in a **High Volatility** panic often expands to +5.0 (Momentum). The Z-score alone is blind to regime.
*   **The Solution**: The Meta Model sees the regime.
    *   **Feature 1: Volatility Ratio**. Is the active leg moving 3x faster than the passive leg? (Danger).
    *   **Feature 2: Beta Stability**. Is the correlation breaking down? (Danger).
    *   **Feature 3: Trend Strength**. Is the move parabolic? (Danger for Reversion, Good for Momentum).

### C. The "Hourly Edge" (H1)
We deploy on the **Hourly (H1)** timeframe.
*   **Why not 5m?** Spread costs (~3bps) destroy the alpha (~5bps).
*   **Why not H4?** Too slow. We miss the intraday "V-Shape" recoveries.
*   **H1 Sweet Spot**: We capture substantial moves (~50-100 bps) where the 3bps spread is negligible. Holding period is ~6 days.

---

## 3. The 2025 Grand Scan (Performance Audit) 📊

*Based on Full H1 History (2018-2025).*

| Rank | Pair | Logic | Win Rate | Mean Net PnL | Verdict |
|---|---|---|---|---|---|
| **1** | **Gold / Oil** (`XAU/BCO`) | **Commodity Cycle** | **63%** | **+79 bps** | **Alpha King**. The most robust signal in existence. |
| **2** | **CAC 40 / NZD** (`FRX/NZD`) | **Risk On/Off** | **59%** | **+76 bps** | **Efficiency King**. Cheap cost, clean moves. |
| **3** | **Oil / Silver** (`BCO/XAG`) | **Inflation** | **58%** | **+43 bps** | **Volume King**. High frequency compounding. |
| **4** | **CAC 40 / AUDCAD** | **Global Macro** | **57%** | **+60 bps** | Reliable Index play. |

---

## 4. Execution Rules ⚙️

### A. Entry Protocol
1.  **Monitor**: H1 Closing Prices.
2.  **Update**: Run `Inference Script` to update Kalman States.
3.  **Trigger**: If Z-Score > 1.5 AND Volatility > 2.5 (Annualized).
4.  **Validate**: Pass context to **CatBoost Model**.
5.  **Execute: The Dual-Hypothesis Test**.
    *   *The Question*: "Is this Z-Score of 2.0 a peak (Reversion) or a breakout (Momentum)?"
    *   *The Method*: We construct **two feature vectors** for the same event and feed both to the Meta Model:
        *   **Hypothesis A (MOM)**: "If I bet on expansion (Target: Z->3.5), what is my expected PnL?"
        *   **Hypothesis B (REV)**: "If I bet on contraction (Target: Z->0.0), what is my expected PnL?"
    *   *Selection Logic*:
        *   The Model outputs a predicted PnL for A and B.
        *   **Winner Takes All**: We select the strategy with the higher predicted PnL, *provided it exceeds the +20 bps hurdle*.
        *   *Context*: 
            *   **Momentum Wins** when Trend Strength > 0.02 (Parabolic) and Volatility is High (Panic).
            *   **Reversion Wins** when Trend Strength < 0.01 (Rangebound) and Volatility is Low (Mean Reverting).
    *   *Result*: The model dynamically adapts to the regime, fighting the trend only when it's weak.

### B. Exit Protocol
1.  **Profit Take**: When Z-Score returns to 0 (Mean Reversion) or Model Signal Flips.
2.  **Stop Loss**: If Z-Score exceeds 3.5 (Structural Break).
3.  **Circuit Breaker**: If 3 consecutive losses on a pair, pause pair for 30 days.

### C. Seasonality Filter (The "Kill Zone")
*   **Do NOT Enter** between **21:00 UTC and 23:00 UTC**.
*   *Reason*: Liquidity drops between US Close and Asian Open. Spreads widen, noise increases.

---

## 5. Deployment Guide 🛠️

To run the strategy, use the verified scripts:

| Component | Script | Purpose |
|---|---|---|
| **Inference Engine** | `scripts/inference_meta_model.py` | **Live Signal Generator**. Calculates Features -> Runs Model -> Outputs Action. |
| **Model File** | `models/meta_model_h1/catboost_h1_reg.cbm` | The "Brain". Trained H1 Regressor. |
| **Training** | `scripts/train_meta_model_h1.py` | To retrain the model with new data. |
| **Data Builder** | `scripts/build_all_1h_data.py` | To update the underlying parquet files. |
| **Research Tool** | `scripts/explore_h1_meta.py` | **Deep Dive Analysis**. Generates the Vol/Trend stats (The "V-Shape"). |

> [!IMPORTANT]
> **Daily Routine**:
> 1.  Update 1h Data (Download/Process).
> 2.  Run `inference_meta_model.py`.
> 3.  Execute signals > 20bps.

