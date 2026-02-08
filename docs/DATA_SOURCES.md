# Data Acquisition Guide 📊

To feed the `~/Desktop/tick` ingestion pipeline, we recommend the following sources for 1-minute OHLC and Tick data.

## 1. FX & Metals (Free / Standard)
**Source**: [HistData.com](http://www.histdata.com/)
**Coverage**: 66 Forex Pairs, Gold (XAUUSD), Silver (XAGUSD), WTI Oil, Brent Oil.
**Format**: "Generic ASCII 1-Minute" (M1) or "Tick Data".
**Ingestion**:
1.  Download the ZIP file.
2.  Unzip to CSV.
3.  We need to convert this CSV to Parquet with columns (`timestamp`, `bid`, `ask`).
    *   *Note: HistData M1 format is `DateTime, Open, High, Low, Close, Volume`.*
    *   *Note: HistData Tick format is `DateTime, Bid, Ask, Volume`.* -> **Preferred**.

## 2. Indices & CFDs (Broker Specific)
**Source**: Your Trading Broker (e.g., FTMO, EightCap, Pepperstone)
**Coverage**: SPX500, NAS100, US30, GER40, UK100, Crypto.
**Reason**: CFD prices are **not centralized**. Quotes vary significantly between brokers (up to 10-20 points on DAX/Dow). Using a different data source than your execution venue can lead to "Phantom Signals" (Signal on chart, no fill in reality).
**Method**:
1.  **MetaTrader 4/5**:
    *   Tools -> History Center (F2).
    *   Select Symbol -> 1 Minute.
    *   "Download" (gets MetaQuotes data - okay quality).
    *   "Export" -> Save as CSV.
2.  **TickSuite / QuantDataManager**: 3rd party tools to download Dukascopy/TickStory data (High quality, but may not match your broker).

## 3. Futures (Premium / Institutional)
**Source**: [Databento](https://databento.com/)
**Coverage**: CME (ES, NQ, CL, GC), Eurex (DAX, Bund).
**Cost**: Pay-per-GB (very affordable).
**Format**: First-class support for generic Parquet.
**Use Case**: If we switch to Futures execution (Prop Firms like Topstep/Apex).

## Current Pipeline Support
Our script `scripts/build_all_1m_data.py` expects **Parquet** files in `~/Desktop/tick/{SYMBOL}/*_ticks.parquet` with columns:
- `timestamp` (datetime)
- `bid` (float)
- `ask` (float)

If you download **OHLC** data (instead of Tick), we need to adapt the script to skip the "resample" step and just load the OHLC directly.
