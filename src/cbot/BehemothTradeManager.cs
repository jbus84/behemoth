using System;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using System.Collections.Generic;
using cAlgo.API;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    /// <summary>
    /// BehemothTradeManager — Tick-based OCO cBot.
    /// Pulls historical ticks on startup, POSTs them to the Behemoth API /backfill endpoint
    /// for state warmup. Then streams live ticks to /ticks and triggers predictions.
    /// </summary>
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class BehemothTradeManager : Robot
    {
        [Parameter("API Base URL", DefaultValue = "http://127.0.0.1:8000")]
        public string BaseUrl { get; set; }

        [Parameter("Lot Size", DefaultValue = 0.05, MinValue = 0.01, Step = 0.01)]
        public double LotSize { get; set; }

        [Parameter("Warmup Ticks", DefaultValue = 30000, MinValue = 100)]
        public int WarmupTicks { get; set; }

        private HttpClient _client;
        private Ticks _historicalTicks;

        // Map broker name (e.g. XBRUSD) to internal API name (e.g. BCOUSD)
        // If not mapped, uses broker name directly.
        private string GetInternalSymbolName(string brokerName)
        {
            if (brokerName == "XBRUSD") return "BCOUSD";
            if (brokerName == "US 500") return "SPXUSD";
            if (brokerName == "US 30") return "UDXUSD";
            if (brokerName == "US TECH 100") return "NSXUSD";
            if (brokerName == "GERMANY 40") return "GRXEUR";
            if (brokerName == "FRANCE 40") return "FRXEUR";
            if (brokerName == "UK 100") return "UKXGBP";
            if (brokerName == "JAPAN 225") return "JPXJPY";
            if (brokerName == "HONG KONG 50") return "HKXHKD";
            return brokerName;
        }

        private static readonly JsonSerializerOptions _jsonOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        private string _internalSymbol;

        protected override void OnStart()
        {
            try
            {
                _client = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
                _internalSymbol = GetInternalSymbolName(Symbol.Name);
                
                Print($"[INIT] Starting Tick Backfill for {_internalSymbol} (Broker: {Symbol.Name})");
                
                _historicalTicks = MarketData.GetTicks();
                
                int loadAttempts = 0;
                while (_historicalTicks.Count < WarmupTicks && loadAttempts < 500)
                {
                    int before = _historicalTicks.Count;
                    _historicalTicks.LoadMoreHistory();
                    if (_historicalTicks.Count == before) 
                    {
                        Print($"[INIT] Reached max available history: {_historicalTicks.Count} ticks.");
                        break;
                    }
                    loadAttempts++;
                }

                Print($"[INIT] Loaded {_historicalTicks.Count} historical ticks. Constructing backfill payload...");

                int startIdx = Math.Max(0, _historicalTicks.Count - WarmupTicks);
                int countToProcess = _historicalTicks.Count - startIdx;
                var tickList = new List<object>(countToProcess);

                for (int i = startIdx; i < _historicalTicks.Count; i++)
                {
                    tickList.Add(new
                    {
                        symbol = _internalSymbol,
                        timestamp = _historicalTicks[i].Time.ToUniversalTime().ToString("O"),
                        bid = _historicalTicks[i].Bid,
                        ask = _historicalTicks[i].Ask,
                        tick_volume = 1.0 // cTrader API doesn't expose strict tick volume per individual tick natively
                    });
                }

                var payload = new
                {
                    symbol = _internalSymbol,
                    bar_ticks = 100, // Sync with backend aggregator schema
                    ticks = tickList
                };

                var json = JsonSerializer.Serialize(payload, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                Print($"[POST] Sending {tickList.Count} ticks to /backfill ({json.Length / 1024}KB)");
                var task = _client.PostAsync($"{BaseUrl}/backfill", content);
                if (task.Wait(TimeSpan.FromSeconds(50)))
                {
                    var resp = task.Result;
                    var body = resp.Content.ReadAsStringAsync().Result;
                    Print($"[BACKFILL RESPONSE] {resp.StatusCode}: {body}");
                }
                else
                {
                    Print("[ERROR] Backfill request timed out.");
                }
            }
            catch (Exception ex)
            {
                Print($"[FATAL] OnStart error: {ex}");
            }
        }

        protected override void OnTick()
        {
            try
            {
                var now = Server.Time;

                // Friday protection
                if (now.DayOfWeek == DayOfWeek.Friday)
                {
                    if (now.Hour >= 21 && now.Minute >= 45)
                    {
                        foreach (var pos in Positions.Where(p => p.SymbolName == Symbol.Name && p.Label != null && p.Label.StartsWith("Oco_")))
                        {
                            var closeOk = ClosePosition(pos);
                        }
                        return;
                    }
                    if (now.Hour >= 20) return;
                }

                var lastTick = _historicalTicks.LastValue;

                var payload = new
                {
                    symbol = _internalSymbol,
                    timestamp = lastTick.Time.ToUniversalTime().ToString("O"),
                    bid = lastTick.Bid,
                    ask = lastTick.Ask,
                    tick_volume = 1.0
                };

                var json = JsonSerializer.Serialize(payload, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var task = _client.PostAsync($"{BaseUrl}/ticks", content);
                if (task.Wait(TimeSpan.FromSeconds(2)))
                {
                    var resp = task.Result;
                    if (resp.IsSuccessStatusCode)
                    {
                        var body = resp.Content.ReadAsStringAsync().Result;
                        var tickResp = JsonSerializer.Deserialize<TickResponse>(body, _jsonOpts);
                        if (tickResp != null && tickResp.bar_completed)
                        {
                            Print($"[BAR COMPLETED] Triggering prediction...");
                            TriggerPrediction();
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Print($"[WARN] OnTick fast-fail: {ex.Message}");
            }
        }

        private void TriggerPrediction()
        {
            try
            {
                var payload = new { symbol = _internalSymbol };
                var json = JsonSerializer.Serialize(payload, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var task = _client.PostAsync($"{BaseUrl}/predict", content);
                if (task.Wait(TimeSpan.FromSeconds(5)))
                {
                    var resp = task.Result;
                    if (resp.IsSuccessStatusCode)
                    {
                        var body = resp.Content.ReadAsStringAsync().Result;
                        var predictions = JsonSerializer.Deserialize<List<OcoPrediction>>(body, _jsonOpts);
                        
                        if (predictions != null)
                        {
                            ProcessPredictions(predictions);
                        }
                    }
                    else
                    {
                        Print($"[PREDICT ERROR] {resp.StatusCode}");
                    }
                }
            }
            catch (Exception ex)
            {
                Print($"[ERROR] TriggerPrediction failed: {ex.Message}");
            }
        }

        private void ProcessPredictions(List<OcoPrediction> predictions)
        {
            foreach (var pred in predictions)
            {
                if (pred.selected_exec == 1)
                {
                    Print($"[EXECUTE] {pred.candidate_uid} (Prob: {pred.pred_prob:F3} >= Thr: {pred.threshold_exec:F3})");
                    
                    // The candidate_uid format is: library|symbol|bar_ticks|hN|state_id
                    // e.g. oco_first_touch_clean|EURUSD|100|h5|oco_first_touch_clean__low_abs_vol__k2
                    
                    try 
                    {
                        var parts = pred.candidate_uid.Split('|');
                        var hPart = parts.FirstOrDefault(p => p.StartsWith("h")); // e.g. "h5"
                        // Parse horizon (default to 6 if failed)
                        int horizon = 6;
                        if (hPart != null && hPart.Length > 1) int.TryParse(hPart.Substring(1), out horizon);
                        
                        // Parse barrier length from state_id part if possible, or assume config defaults
                        // But wait! The actual model doesn't tell us direction (Long/Short). 
                        // It predicts "absolute opportunity" which implies we place BOTH a BuyStop and SellStop! 
                        // That's what OCO (One Cancels Other) means.
                        
                        // Place OCO Orders
                        PlaceOcoOrders(pred.candidate_uid, horizon);
                        break; // Only execute the top candidate that passed threshold
                    }
                    catch (Exception ex)
                    {
                        Print($"[EXEC ERROR] Could not place OCO for {pred.candidate_uid}: {ex.Message}");
                    }
                }
            }
        }

        private void PlaceOcoOrders(string candidateUid, int horizonBars)
        {
            // OCO Logic: Place Buy Stop above current price, Sell Stop below
            // Since we don't have the exact barrier pip size easily extracted from UID in C# without reliable parsing,
            // we could parse it from the state string (e.g. k2 = barrier 2).
            double barrierPips = 2.0; 
            if (candidateUid.Contains("k3")) barrierPips = 3.0;
            
            double volume = Symbol.QuantityToVolumeInUnits(LotSize);
            string groupLabel = $"Oco_{candidateUid}_{Server.Time:yyyyMMddHHmmss}";

            double buyPrice = Symbol.Ask + (barrierPips * Symbol.PipSize);
            double sellPrice = Symbol.Bid - (barrierPips * Symbol.PipSize);

            // Execute as Async to avoid blocking
            PlaceStopOrderAsync(TradeType.Buy, Symbol.Name, volume, buyPrice, groupLabel);
            PlaceStopOrderAsync(TradeType.Sell, Symbol.Name, volume, sellPrice, groupLabel);
            
            Print($"[OCO PLACED] {groupLabel} | BuyStop: {buyPrice:F4} | SellStop: {sellPrice:F4}");
        }

        protected override void OnStop()
        {
            _client?.Dispose();
        }
    }

    public class TickResponse
    {
        public bool ok { get; set; }
        public string symbol { get; set; }
        public bool bar_completed { get; set; }
        public int bar_count { get; set; }
    }

    public class OcoPrediction
    {
        public string symbol { get; set; }
        public string candidate_uid { get; set; }
        public double pred_prob { get; set; }
        public double threshold_exec { get; set; }
        public int selected_exec { get; set; }
        public string threshold_source { get; set; }
        public string model_month { get; set; }
    }
}
