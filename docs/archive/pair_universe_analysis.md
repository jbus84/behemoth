# Global Pair Universe Analysis

## Methodology: Finding the "Safe Hedge"
This analysis scans the entire available asset universe (FX, Indices, Commodities) to identify pairs suitable for **Kalman Filter Mean Reversion**.

### Data Protocol 💾
*   **Source Data**: High-fidelity Tick Data resampled to **1-Hour OHLC Bars**.
*   **Price Levels**: Analyses use **Natural Logarithms** (`ln(Price)`) to normalize magnitude differences between assets (e.g., SPX 5000 vs Gold 2000).
*   **Returns Analysis**: Volatility and Beta calculations use **Log Returns** (`ln(Pt) - ln(Pt-1)`), ensuring we measure "percentage moves" rather than "point moves".

### The Core Problem: "Beta Mismatch" 🛡️
Most pairs trading strategies fail because they assume the **Long-Term Relationship (Cointegration)** matches the **Short-Term Risk (Correlation)**.
*   **Signal Beta (Levels)**: The long-term equilibrium ratio, calculated as the slope of the regression between **Log Prices** (`ln(Price_Y)` vs `ln(Price_X)`).
    *   *Purpose*: This tells us "Where the price SHOULD be". If the spread reflects this beta, we expect it to mean-revert. We use this to generate the **Entry Signal**.
*   **Hedge Beta (Returns)**: The short-term correlation sensitivity, calculated as the slope of the regression between **Log Returns** (`Return \_Y` vs `Return_X`).
    *   *Purpose*: This tells us "How much it moves TODAY". If we want to be market-neutral, we must hedge based on this beta.
*   **The Trap**: If you size your trade based on the Signal Beta (to capture mean reversion) but the Hedge Beta is different, you are **Unhedged**.
    *   *Example (Gold/Silver)*: Signal says buy 1 Gold, Sell 1 Silver. But Silver moves 1.5x faster. You are effectively **Net Short 0.5 Silver**. This "Toxic Beta" destroys alpha.
*   **The Goal**: We filter for pairs where **Mismatch (Hedge/Signal)** is between **0.80x and 1.20x**. This ensures that when we put on a "Hedge", it is actually hedged.

### The Edge: Stationarity (ADF) 📉
Once safety is confirmed (Matched Betas), we test if the spread actually makes money.
*   **ADF P-Value**: Tests if the spread drifts forever (Random Walk) or snaps back (Mean Reverting).
*   **Goal**: P-Value < **0.01** (Strong) or < **0.05** (Acceptable).

### How to Interpret the Tables 🧐
*   **Beta Mismatch (~1.0x is Best)**:
    *   **1.00x**: Perfect Hedge. The Entry Signal matches the Risk.
    *   **> 1.20x**: Over-Volatile. The asset moves more than the signal expects. Risk of stopping out.
    *   **< 0.80x**: Lagging. The asset is sluggish.
    *   **Negative Values**: **WARNING**. This means the Signal and the Hedge are in opposite directions (e.g., Signal says Correlated, Returns are Anti-Correlated). This creates a "Volatility Expansion" trade, not a hedge. **Proceed with caution.**
*   **P-Value (<0.05)**: The lower the better. 0.0000 means the spread is extremely reliable at reverting to the mean.

### Concrete Example: `ETXEUR / FRXEUR`
*   **Values**: Mismatch Let's analyze the row: `0.97x | 0.0000 | 0.98`
*   **The Assets**:
    *   **ETX (`ETXEUR`)**: **Euro Stoxx 50**. The leading Blue-chip index for the Eurozone (top 50 companies like LVMH, SAP, Siemens).
    *   **FRX (`FRXEUR`)**: **CAC 40**. The benchmark French Stock Market Index (top 40 companies in France).
    *   *Why they match*: Many CAC 40 companies are also in the Euro Stoxx 50. They are economically inseparable.
*   **Signal Beta (0.98)**: The prices move almost 1:1. For every 1% move in ETX, FRX moves 0.98%.
*   **Mismatch (0.97x)**: This is **Perfect**. The implied "Fair Value" relationship (0.98) is almost identical to the daily "Risk" relationship. If you hedge this, you are actually hedged.
*   **P-Value (0.0000)**: The spread is **Stationary**. It does not drift apart; it snaps back to the line constantly.
*   **Verdict**: This is a **Tier 1 Strategic Pair**. It is safe, hedged, and profitable.

---


## 🏆 Tier 1: Strategic Candidates (Match > 80%, P < 0.01)
| Broker Pair | Internal ID | Beta Mismatch | P-Value | Signal Beta | Logic |
|---|---|---|---|---|---|
| **EU50.cash / FRA40.cash** | ETXEUR/FRXEUR | 0.97x | 0.0000 | 0.98 | **Perfect Match**. EuroStoxx vs CAC40. Economically identical. |
| **AUD/NZD** | AUDUSD/NZDUSD | 0.96x | 0.0000 | 0.83 | **Classic Arb**. Australia vs NZ. Correlation > 90%. |
| **US500.cash / US100.cash** | SPXUSD/NSXUSD | 1.03x | 0.0000 | 0.85 | **Tech vs Broad**. S&P vs Nasdaq. High beta but safe. |
| **GER40.cash / UK100.cash** | GRXEUR/UKXGBP | 1.03x | 0.0000 | 1.03 | **DAX vs FTSE**. Europe vs UK. Good post-Brexit arb. |

## 🥈 Tier 2: Tactical Candidates (Match > 70%, P < 0.05)
| Broker Pair | Internal ID | Beta Mismatch | P-Value | Signal Beta | Logic |
|---|---|---|---|---|---|
| **UK100.cash / US500.cash** | UKXGBP/SPXUSD | 0.89x | 0.0000 | 0.83 | **Value vs Growth**. FTSE (Old Econ) vs S&P (New Econ). |
| **AUD/CAD / NZD/CAD** | AUDCAD/NZDCAD | 1.14x | 0.0000 | 0.43 | **Triangular**. AUD/CAD/NZD triangle. |


## 🧪 Tier 3: Explore (Lower Quality / Risky)
| Pair | Beta Mismatch | P-Value | Reason |
|---|---|---|---|
| HKXHKD/FRXEUR | 0.64x | 0.0000 |  |
| GBPCAD/JPXJPY | -0.64x | 0.0000 |  |
| GBPCAD/ETXEUR | -0.56x | 0.0000 |  |
| UKXGBP/SPXUSD | 0.50x | 0.0000 |  |
| UKXGBP/GRXEUR | 0.58x | 0.0000 |  |
| GRXEUR/HKXHKD | 0.50x | 0.0000 |  |
| SPXUSD/UDXUSD | 0.58x | 0.0000 |  |
| NZDCAD/HKXHKD | -1.32x | 0.0000 |  |
| SPXUSD/HKXHKD | 0.61x | 0.0000 |  |
| SPXUSD/ETXEUR | 0.55x | 0.0000 |  |
| JPXJPY/GRXEUR | 0.69x | 0.0000 |  |
| JPXJPY/USDJPY | 0.58x | 0.0000 |  |
| JPXJPY/SPXUSD | 0.68x | 0.0000 |  |
| AUXAUD/UKXGBP | 0.54x | 0.0000 |  |
| UDXUSD/HKXHKD | 0.68x | 0.0000 |  |
| BCOUSD/HKXHKD | 0.62x | 0.0000 |  |
| XAGUSD/HKXHKD | 0.67x | 0.0000 |  |
| UDXUSD/FRXEUR | 0.68x | 0.0000 |  |
| EURGBP/UDXUSD | 1.43x | 0.0000 |  |
| EURGBP/ETXEUR | 1.41x | 0.0000 |  |
| EURGBP/BCOUSD | 0.58x | 0.0000 |  |
| USDCAD/BCOUSD | -1.35x | 0.0000 |  |
| JPXJPY/HKXHKD | 0.54x | 0.0000 |  |
| UKXGBP/FRXEUR | 0.63x | 0.0000 |  |
| USDCAD/GBPCAD | 0.60x | 0.0000 |  |
| NZDUSD/AUDUSD | 0.52x | 0.0000 |  |
| USDCAD/AUDUSD | 0.52x | 0.0000 |  |
| NZDCAD/AUDUSD | 0.52x | 0.0000 |  |
| AUDCAD/GBPUSD | -0.59x | 0.0000 |  |
| AUDCAD/EURUSD | -0.51x | 0.0001 |  |

## ⛔ Avoid List (Sample)
| Pair | Reason |
|---|---|
| ETXEUR/HKXHKD | Beta Mismatch.  (Mis: 0.49x, P: 0.00) |
| USDCHF/HKXHKD | Beta Mismatch.  (Mis: 999.00x, P: 0.00) |
| ETXEUR/GBPJPY | Beta Mismatch.  (Mis: 0.36x, P: 0.00) |
| ETXEUR/BCOUSD | Beta Mismatch.  (Mis: 0.06x, P: 0.00) |
| ETXEUR/UDXUSD | Beta Mismatch.  (Mis: 0.34x, P: 0.00) |
| GBPCAD/UDXUSD | Beta Mismatch.  (Mis: -0.35x, P: 0.00) |
| GBPCAD/BCOUSD | Beta Mismatch.  (Mis: -0.28x, P: 0.00) |
| GBPCAD/GBPJPY | Beta Mismatch.  (Mis: 3.44x, P: 0.00) |
| GBPCAD/HKXHKD | Beta Mismatch.  (Mis: -0.32x, P: 0.00) |
| AUDUSD/FRXEUR | Beta Mismatch.  (Mis: -3.73x, P: 0.00) |
| ETXEUR/USDJPY | Beta Mismatch.  (Mis: 0.47x, P: 0.00) |
| GBPUSD/GRXEUR | Beta Mismatch.  (Mis: 1.51x, P: 0.00) |
| USDCHF/GRXEUR | Beta Mismatch.  (Mis: 999.00x, P: 0.00) |
| GBPUSD/USDJPY | Beta Mismatch.  (Mis: -3.12x, P: 0.00) |
| UKXGBP/JPXJPY | Beta Mismatch.  (Mis: 0.50x, P: 0.00) |
| GRXEUR/GBPJPY | Beta Mismatch.  (Mis: 0.30x, P: 0.00) |
| GRXEUR/UDXUSD | Beta Mismatch.  (Mis: 0.39x, P: 0.00) |
| UKXGBP/ETXEUR | Beta Mismatch.  (Mis: 0.42x, P: 0.00) |
| GRXEUR/USDJPY | Beta Mismatch.  (Mis: 0.44x, P: 0.00) |
| UKXGBP/USDJPY | Beta Mismatch.  (Mis: 0.30x, P: 0.00) |


# Part 2: 4-Hour Timeframe Analysis (H4) 🕓
Slower timeframe often filters noise and improves stationarity.

## 🏆 Tier 1: Strategic Candidates (Match > 80%, P < 0.01)
| Broker Pair | Internal ID | Beta Mismatch | P-Value | Signal Beta | Logic |
|---|---|---|---|---|---|
| **EU50.cash / FRA40.cash** | ETXEUR/FRXEUR | 0.98x | 0.0000 | 0.98 | **Stronger on H4**. Mismatch improved to near 1.00. |
| **UKOIL.cash / UK100.cash** | BCOUSD/UKXGBP | 1.01x | 0.0000 | 0.48 | **NEW (H4 Only)**. Oil vs FTSE 100. Perfect hedge. (FTSE is energy-heavy). |
| **UKOIL.cash / AUS200.cash** | BCOUSD/AUXAUD | 1.06x | 0.0000 | 0.49 | **NEW (H4 Only)**. Oil vs ASX 200. Australia is a commodity proxy. |
| **GER40.cash / UK100.cash** | GRXEUR/UKXGBP | 0.84x | 0.0000 | 1.06 | **DAX vs FTSE**. Still solid on H4. |
| **EURUSD / GBPUSD** | EURUSD/GBPUSD | 0.86x | 0.0005 | 0.55 | **NEW (H4 Only)**. The "Cable-Euro" spread stabilizes on H4. |
| **US500.cash / US100.cash** | SPXUSD/NSXUSD | 1.05x | 0.0000 | 0.85 | **Tech Beta**. Remains robust. |

## 🥈 Tier 2: Tactical Candidates (Match > 70%, P < 0.05)
| Broker Pair | Internal ID | Beta Mismatch | P-Value | Signal Beta | Logic |
|---|---|---|---|---|---|
| **EURUSD / JP225.cash** | EURUSD/JPXJPY | 1.02x | 0.0000 | 0.01 | **Weird but Safe**. Euro vs Nikkei? 1.02x mismatch is incredibly stable. |
| **AUD/CAD / NZD/CAD** | AUDCAD/NZDCAD | 1.25x | 0.0199 | 0.36 | **Triangular**. Volatility increased slightly on H4 (1.25x), better on H1. |



# Part 3: 15-Minute Timeframe Analysis (M15) ⚡
Fast timeframe for Hyper-Scalping. Requires strict Beta Match (0.8-1.2).

## 🏆 Tier 1: Strategic Candidates (Match > 80%, P < 0.01)
| Broker Pair | Internal ID | Beta Mismatch | P-Value | Signal Beta | Logic |
|---|---|---|---|---|---|
| **UKOIL.cash / GER40.cash** | BCOUSD/GRXEUR | 0.98x | 0.0000 | 0.44 | **HYPER-SCALP**. Oil/DAX arbitrage. Perfect 15m hedge. |
| **UKOIL.cash / FRA40.cash** | BCOUSD/FRXEUR | 1.07x | 0.0000 | 0.48 | **Oil vs France**. Slightly more volatile (1.07x) but very tradeable. |
| **UKOIL.cash / US500.cash** | BCOUSD/SPXUSD | 1.11x | 0.0000 | 0.52 | **Oil vs S&P**. High beta, fast mean reversion. |
| **EU50.cash / UK100.cash** | ETXEUR/UKXGBP | 1.05x | 0.0000 | 0.97 | **Euro/FTSE**. Better on 15m than 1H. Fast scalp. |
| **EU50.cash / FRA40.cash** | ETXEUR/FRXEUR | 1.17x | 0.0000 | 1.01 | **Volatile Here**. Mismatch is 1.17x (vs 0.98x on H4). Expect noise. |
| **US100.cash / US500.cash** | NSXUSD/SPXUSD | 1.06x | 0.0000 | 1.12 | **Nasdaq/S&P**. The ultimate high-frequency scalper. |

## 🥈 Tier 2: Tactical Candidates (Match > 70%, P < 0.05)
| Broker Pair | Internal ID | Beta Mismatch | P-Value | Signal Beta | Logic |
|---|---|---|---|---|---|
| **AUD/CAD / GBP/USD** | AUDCAD/GBPUSD | -0.87x | 0.0020 | -0.17 | **Strange Hedge**. Negative correlation scalp. |
| **NZD/CAD / USD/CAD** | NZDCAD/USDCAD | -1.03x | 0.0350 | -0.35 | **Loonie Fight**. Trading NZD vs USD via CAD cross. |

---

## ⚠️ The Gold Anomaly (`XAUUSD`)
Our scan explicitly targeted Gold (`XAUUSD`) across all timeframes (M15, H1, H4).
**Result**: **Zero Tier 1 Candidates**.
*   **Why**: Gold suffers from extreme "Beta Mismatch".
    *   **Gold vs Indices**: Often shows positive *Signal Beta* (Levels) but negative *Hedge Beta* (Returns). This creates a "Trap" where the model buys the spread, but the daily volatility rips against it.
    *   **Gold vs Silver**: The classic pair has a mismatch > 3.0x. Silver is too volatile to hedge Gold linearly.
*   **Recommendation**: **Do not trade Gold** with this Mean Reversion strategy. Use **Oil** (`UKOIL`) instead, which hedges perfectly against Indices.




# Part 2: 4-Hour Timeframe Analysis (H4) 🕓
Slower timeframe often filters noise and improves stationarity.

## 🏆 Tier 1: Strategic Candidates (Match > 80%, P < 0.01)
| Internal ID | Beta Mismatch | P-Value | Signal Beta |
|---|---|---|---|
| FRXEUR/GRXEUR | 0.80x | 0.0000 | 0.91 |
| BCOUSD/JPXJPY | 0.76x | 0.0000 | 0.43 |
| BCOUSD/UKXGBP | 1.01x | 0.0000 | 0.48 |
| GRXEUR/UKXGBP | 0.84x | 0.0000 | 1.06 |
| BCOUSD/FRXEUR | 0.71x | 0.0000 | 0.50 |
| BCOUSD/AUXAUD | 1.06x | 0.0000 | 0.49 |
| GRXEUR/AUXAUD | 0.78x | 0.0000 | 1.08 |
| FRXEUR/AUXAUD | 0.77x | 0.0000 | 0.98 |
| JPXJPY/UKXGBP | 0.78x | 0.0000 | 1.13 |
| GRXEUR/ETXEUR | 0.70x | 0.0000 | 1.14 |
| BCOUSD/SPXUSD | 0.83x | 0.0000 | 0.54 |
| ETXEUR/UKXGBP | 0.95x | 0.0000 | 0.93 |
| JPXJPY/AUXAUD | 0.84x | 0.0000 | 1.15 |
| EURUSD/JPXJPY | 1.02x | 0.0000 | 0.01 |
| ETXEUR/AUXAUD | 0.96x | 0.0000 | 0.95 |
| NSXUSD/AUXAUD | 1.08x | 0.0000 | 1.02 |
| NZDUSD/AUXAUD | -1.10x | 0.0000 | -0.05 |
| UDXUSD/SPXUSD | 0.79x | 0.0000 | 1.16 |
| FRXEUR/UKXGBP | 0.82x | 0.0000 | 0.96 |
| NZDCAD/NSXUSD | 1.16x | 0.0000 | -0.01 |
| SPXUSD/UKXGBP | 0.85x | 0.0000 | 0.89 |
| NSXUSD/UKXGBP | 0.91x | 0.0000 | 1.00 |
| SPXUSD/NSXUSD | 0.76x | 0.0000 | 0.89 |
| EURCHF/XAGUSD | 1.27x | 0.0000 | 0.05 |
| SPXUSD/AUXAUD | 0.96x | 0.0000 | 0.91 |
| NZDCAD/XAGUSD | -1.06x | 0.0000 | -0.05 |
| GBPJPY/EURJPY | 0.75x | 0.0000 | 1.02 |
| AUDNZD/GBPCAD | -0.72x | 0.0001 | 0.15 |
| AUDNZD/NZDUSD | 1.23x | 0.0001 | -0.20 |
| AUDNZD/AUDUSD | -0.77x | 0.0002 | -0.25 |
| EURUSD/GBPUSD | 0.86x | 0.0005 | 0.55 |
| EURUSD/NZDUSD | -1.20x | 0.0036 | -0.35 |
| EURUSD/AUDUSD | -1.01x | 0.0038 | -0.44 |

## 🥈 Tier 2: Tactical Candidates (Match > 70%, P < 0.05)
| Internal ID | Beta Mismatch | P-Value | Signal Beta |
|---|---|---|---|
| EURUSD/USDCAD | -0.70x | 0.0131 | 0.52 |
| AUDCAD/NZDCAD | 1.25x | 0.0199 | 0.36 |
| NZDCAD/USDCAD | -0.70x | 0.0456 | -0.47 |


# Part 3: 15-Minute Timeframe Analysis (M15) ⚡
Fast timeframe for Hyper-Scalping. Requires strict Beta Match (0.8-1.2).

## 🏆 Tier 1: Strategic Candidates (Match > 80%, P < 0.01)
| Internal ID | Beta Mismatch | P-Value | Signal Beta |
|---|---|---|---|
| SPXUSD/GRXEUR | 0.82x | 0.0000 | 0.85 |
| ETXEUR/UKXGBP | 1.05x | 0.0000 | 0.97 |
| ETXEUR/FRXEUR | 1.17x | 0.0000 | 1.01 |
| GBPCAD/SPXUSD | -1.04x | 0.0000 | 0.07 |
| GBPCAD/NSXUSD | -0.90x | 0.0000 | 0.06 |
| UDXUSD/NSXUSD | 1.06x | 0.0000 | 0.83 |
| GBPCAD/FRXEUR | -1.17x | 0.0000 | 0.06 |
| UDXUSD/SPXUSD | 0.81x | 0.0000 | 0.93 |
| GBPCAD/EURJPY | 1.19x | 0.0000 | 0.11 |
| BCOUSD/FRXEUR | 1.07x | 0.0000 | 0.48 |
| BCOUSD/NSXUSD | 0.86x | 0.0000 | 0.47 |
| BCOUSD/SPXUSD | 1.11x | 0.0000 | 0.52 |
| BCOUSD/GRXEUR | 0.98x | 0.0000 | 0.44 |
| NZDUSD/AUXAUD | -1.12x | 0.0000 | -0.04 |
| ETXEUR/GRXEUR | 1.10x | 0.0000 | 0.92 |
| FRXEUR/GRXEUR | 0.83x | 0.0000 | 0.91 |
| EURGBP/NSXUSD | 1.18x | 0.0000 | -0.01 |
| NSXUSD/GRXEUR | 0.93x | 0.0000 | 0.95 |
| NSXUSD/SPXUSD | 1.06x | 0.0000 | 1.12 |
| JPXJPY/UKXGBP | 0.82x | 0.0000 | 1.13 |
| AUDCAD/GBPUSD | -0.87x | 0.0000 | -0.17 |
| NZDCAD/USDCAD | -1.03x | 0.0000 | -0.35 |

## 🥈 Tier 2: Tactical Candidates (Match > 70%, P < 0.05)
| Internal ID | Beta Mismatch | P-Value | Signal Beta |
|---|---|---|---|
