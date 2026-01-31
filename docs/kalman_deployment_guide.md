# Kalman Pairs: Deployment Guide

## 1. The Setup (What you need)
*   **Platform**: Any platform that supports Python (IBKR, QuantConnect) or a spreadsheet with script support.
*   **Data**: Real-time **4-Hour Bars** for:
    *   **Asset Y**: Nasdaq 100 Futures (`NQ`) or ETF (`QQQ`).
    *   **Asset X**: S&P 500 Futures (`ES`) or ETF (`SPY`).
    *   *Note*: Ensure they are liquid and share the same trading hours.

## 2. The State (What you must track)
The Kalman Filter is "Recursive". You must remember two numbers from the previous bar:
1.  **Beta ($\beta$)**: The current hedge ratio.
2.  **Covariance ($P$)**: The uncertainty of your beta.
*   *Initial State*: Start with Beta = 1.0 (or historic mean) and P = 1.0.

## 3. The Algorithm (Every 4 Hours)
When a new bar closes (e.g., 10:00, 14:00, 18:00):
1.  **Fetch Prices**: Get Close($Y_t$) and Close($X_t$). *Use Log Prices*.
2.  **Predict**: $\hat{Y} = \beta_{prev} \times X_t$
3.  **Update Beta**:
    *   $\text{Error} = Y_t - \hat{Y}$
    *   Update $\beta_{new}$ and $P_{new}$ using the Kalman Equations (see `kalman_filter.py`).
4.  **Calculate Spread**:
    *   $\text{Spread}_t = \text{Error}$ (The unexpected move).
5.  **Update Z-Score**:
    *   Add Spread to a rolling window (e.g., last 30 periods).
    *   $Z = \frac{\text{Spread}_t - \text{Mean}(\text{Window})}{\text{StdDev}(\text{Window})}$

## 4. The Trade Logic (Execution)
### Entry Signal
*   **Short Spread ($Z > 2.0$)**: Nasdaq is "Expensive" relative to SP500.
    *   **Action**: SELL Nasdaq / BUY S&P 500.
    *   **Sizing**: For every \$100k of Nasdaq, Buy $(\$100k \times \beta)$ of S&P 500.
*   **Long Spread ($Z < -2.0$)**: Nasdaq is "Cheap".
    *   **Action**: BUY Nasdaq / SELL S&P 500.
    *   **Sizing**: For every \$100k of Nasdaq, Sell $(\$100k \times \beta)$ of S&P 500.

### Exit Signal
*   **Profit Take**: When $Z$ crosses **0.0** (Mean Reversion).
*   **Time Stop**: If trade lasts > **12 Hours** (3 bars) without profit.
    *   *Why?* If mean reversion doesn't happen quickly, the regime might have fundamentally broken.

## 5. Important Rules
1.  **Beta Stability**: If Beta changes by > 10% in one day, **Stay Flat**. (Volatile correlation = Danger).
2.  **News Filter**: Do not open new trades 30 mins before Tier-1 Macro (FOMC, CPI).
3.  **Liquidity**: Only trade during "Liquid Hours" (US Session + European Overlap).

## 6. Example (Walkthrough)
*   **10:00 AM**: Nasdaq (\$20,000) and SP500 (\$5,800).
*   **Kalman says**: Beta is **1.20**. Z-Score is **+2.5** (Sell Signal).
*   **Trade**:
    *   Sell 1 NQ Contract (Notional $\approx$ \$400k).
    *   Buy ES Contracts to match $(\$400k \times 1.20 = \$480k)$.
*   **14:00 PM**: Prices move. Z-Score drops to **0.1**.
*   **Action**: Close both legs. Capture the spread convergence.
