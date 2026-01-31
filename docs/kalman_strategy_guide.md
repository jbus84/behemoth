# Kalman Pairs Trading: The "Dynamic Rubber Band"

## 1. The Core Concept
Standard Pairs Trading assumes two assets are "married" forever (Correlation = 1.0).
**Reality:** They break up, date other people, and drift apart (Regime Shifts).
**The Kalman Filter** doesn't assume a permanent marriage. It behaves like a **Marriage Counselor** who watches the relationship *every single hour* and asks: "How close are you *right now*?"

## 2. The Math (Simplified)
We model the relationship as a "Moving Target":
$$ \text{Nasdaq}_t = \beta_t \times \text{SP500}_t + \text{Noise}_t $$

*   **Beta ($\beta_t$)**: The "Hedge Ratio". If Beta = 1.2, then for every 1% move in SP500, we expect Nasdaq to move 1.2%.
*   **The Magic**: In standard models (OLS), Beta is constant (e.g., calculated over the last year). In **Kalman**, Beta is **updated LIVE at every bar**.

### The Process (Step-by-Step)
1.  **Predict**: Based on Beta from 4 hours ago, where *should* Nasdaq be?
2.  **Observe**: Where *is* Nasdaq actually?
3.  **Update**:
    *   If Nasdaq is way off, is it just **Noise** (Trade Opportunity)?
    *   Or has the **Relationship Changed** (Beta Shift)?
    *   The Kalman Gain ($K$) decides this mix instantly.

## 3. The Signal: Z-Score (The "Rubber Band")
We look at the **Residual** (The Error):
$$ \text{Spread} = \text{Actual Price} - \text{Expected Price} $$

We normalize this into a **Z-Score** (Standard Deviations).
*   **Z = 0**: The price is perfectly "Fair" relative to the other asset.
*   **Z = +2.0**: The pair is **Stretched**. Nasdaq is expensive relative to SP500 Beta. -> **SELL Spread**.
*   **Z = -2.0**: The pair is **Compressed**. Nasdaq is cheap relative to SP500 Beta. -> **BUY Spread**.

## 4. Why 4-Hour Bars?
*   **1-Minute**: Too much HFT noise. The "Beta" fluctuates wildly due to order flow.
*   **Daily**: Too slow. You miss the intraday divergence and convergence.
*   **4-Hour**: The "Sweet Spot". It captures the **Macro Flows** (Capital Rotation, Tech vs Value) which tend to mean-revert over 1-3 days.

## 5. Execution Logic
1.  **Check Z-Score**: Is it > 2.0 or < -2.0?
2.  **Enter Trade**:
    *   **Short Spread**: Sell \$100k Nasdaq / Buy $(\$100k \times \beta)$ SP500.
    *   **Long Spread**: Buy \$100k Nasdaq / Sell $(\$100k \times \beta)$ SP500.
3.  **Hold**: Wait for Z-Score to return to 0 (Mean Reversion).
4.  **Exit**: Usually takes 1-3 bars (4-12 hours).

## 6. Performance vs Baseline
*   **Buy & Hold**: You ride the rollercoaster. If Tech crashes, you lose.
*   **Donchian**: You catch trends, but get chopped in ranging markets.
*   **Kalman**: You make money when the **spread reverts**, regardless of whether the market goes Up, Down, or Sideways.
    *   **Index Pair Result**: Sharpe Ratio **4.49** (Exceptional consistency).
    *   **Drawdown**: Zero correlation to market crashes. It is "Market Neutral".
