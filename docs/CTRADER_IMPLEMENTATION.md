# cTrader Automate: Multi-Asset Implementation 🤖

**Yes**, cTrader Automate (formerly cAlgo) fully supports accessing multiple assets within a single robot. This is essential for the **Meta Model** (Pairs/Spread) strategy.

## Key Concept: `MarketData.GetSeries`

You do not need to run multiple bots. You run **one** bot (e.g., on EURUSD) and it "pulls" data for all other required symbols (e.g., Gold, Oil, Indices).

### 1. Accessing Other Symbols
Inside your `OnStart()` method, you initialize the data series for the assets you want to trade or monitor.

```csharp
using cAlgo.API;

public class MetaModelBot : Robot
{
    private Bars _gold;
    private Bars _oil;
    private Bars _euro;

    protected override void OnStart()
    {
        // 1. Get Bars for other assets (1 Minute)
        // Note: The symbol "Name" must match your broker's symbol exactly (e.g. "XAUUSD" or "Gold").
        _gold = MarketData.GetBars(TimeFrame.Minute, "XAUUSD");
        _oil  = MarketData.GetBars(TimeFrame.Minute, "BCOUSD"); // Brent
        _euro = MarketData.GetBars(TimeFrame.Minute, "EURUSD");

        // 2. Load more history if needed
        // cTrader loads a small amount by default. 
        while (_gold.Count < 500) 
        {
             var loaded = _gold.LoadMoreHistory();
             if (loaded == 0) break;
        }
    }

    protected override void OnBar()
    {
        // This method runs whenever the chart's bar closes. 
        // IF you are running this on EURUSD M1, it runs every 1 minute.
        
        // 3. Synchronize Data
        // Get the time of the just-closed bar
        var time = Bars.OpenTimes.Last(1); 
        
        // Find the index of that time in other series
        var goldIndex = _gold.OpenTimes.GetIndexByTime(time);
        var oilIndex  = _oil.OpenTimes.GetIndexByTime(time);

        if (goldIndex == -1 || oilIndex == -1) 
        {
            Print("Data mismatch/gap");
            return; 
        }

        // 4. Calculate Spread
        double goldPrice = _gold.Close[goldIndex];
        double oilPrice  = _oil.Close[oilIndex];
        
        double spread = Math.Log(goldPrice) - (1.5 * Math.Log(oilPrice)); // Example Beta
        
        Print($"Time: {time}, Gold: {goldPrice}, Oil: {oilPrice}, Spread: {spread}");
    }
}
```

## Important Considerations

### 1. Symbol Names
Symbol names vary by broker.
*   **FTMO**: `GER40`, `US30`, `XAUUSD`
*   **Pepperstone**: `GER40`, `US30`, `XAUUSD`
*   **IC Markets**: `DE40`, `US30`, `XAUUSD`
*   **Check**: Use `Symbol.Name` to verify, or look at the Market Watch info.

### 2. Synchronization
*   **The "Driver"**: The bot runs on **one** chart (e.g., EURUSD). `OnBar` triggers based on *that* chart's ticks.
*   **Holidays/Hours**: If EURUSD is open but US30 is closed (e.g., 22:00 UTC), `OnBar` will fire, but US30 data won't update.
*   **Solution**: Always check `GetIndexByTime(time)`. If it returns `-1`, that asset has no bar for that minute.

### 3. Execution (Multi-Symbol)
You can execute trades on any symbol, not just the chart symbol.

```csharp
// 1. Get the Symbol Object first (Crucial step)
var goldSymbol = MarketData.GetSymbol("XAUUSD");

// 2. Execute on that Symbol
// Note: Volume is in Units (e.g. 1.0 lot might be 100,000 units or 100oz depending on broker).
// Always check goldSymbol.QuantityToVolumeInUnits(1.0) if needed.
ExecuteMarketOrder(TradeType.Buy, goldSymbol, 1.0, "MetaModel Entry", 10, 20);
```

### 4. Backtesting
cTrader's **Multi-Symbol Backtesting** is excellent. It simulates the "Tick" arrival for all subscribed symbols accurately. You can assume that if it works in backtest with `GetBars`, it mimics live behavior closely.
