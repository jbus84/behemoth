using System;
using cAlgo.API;
public class Test : Robot {
    protected override void OnStart() {
        var ticks = MarketData.GetTicks("EURUSD");
        ticks.Tick += args => Print(args.Tick.Bid);
    }
}
