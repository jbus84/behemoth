---
description: How to deploy and debug the Behemoth cBot for cTrader
---

## Deploy cBot

// turbo
1. Run `make deploy-cbot` to copy `src/cbot/BehemothTradeManager.cs` to the cTrader Robots directory
2. Open cTrader Automate and rebuild the bot

## cTrader Paths

- **Source code**: `~/cAlgo/Sources/Robots/BehemothTradeManager/BehemothTradeManager/BehemothTradeManager.cs`
- **Backtest logs**: `~/cAlgo/Data/cBots/BehemothTradeManager/<instance-guid>/Backtesting/`
- **Bot data**: `~/cAlgo/Data/cBots/BehemothTradeManager/`

The instance GUID changes per bot instance. Use `ls ~/cAlgo/Data/cBots/BehemothTradeManager/` to find the right one.

## Run Backtest

1. Ensure the API is running: `make up && make api`
2. Run database migrations: `uv run alembic -c services/api/alembic.ini upgrade head`
3. In cTrader, attach the bot to an M15 chart with parameters:
   - `BarSize = m15`
   - `BaseUrl = http://127.0.0.1:8000`
   - `BarCount = 1500`
   - `LotSize = 0.05`
4. Start the backtest — check bot log tab and API terminal for activity

## Broker Symbol Mapping

The cBot translates internal API names to broker-specific cTrader names:

| Internal | Broker       |
|----------|-------------|
| BCOUSD   | XBRUSD      |
| SPXUSD   | US 500      |
| UDXUSD   | US 30       |
| NSXUSD   | US TECH 100 |
| GRXEUR   | GERMANY 40  |
| FRXEUR   | FRANCE 40   |
| UKXGBP   | UK 100      |
| JPXJPY   | JAPAN 225   |
| HKXHKD   | HONG KONG 50|

FX and metals (EURUSD, XAUUSD, etc.) use the same names.
