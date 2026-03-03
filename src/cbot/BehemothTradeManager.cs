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

        private string GetInternalSymbolName(string brokerName)
        {
            return brokerName;
        }

        private static readonly JsonSerializerOptions _jsonOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        private string _internalSymbol;
        private Dictionary<int, int> _posAgeBars = new Dictionary<int, int>();

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
                            Print($"[BAR COMPLETED] Tracking horizons and triggering prediction...");
                            
                            var ocoPositions = Positions.Where(p => p.SymbolName == Symbol.Name && p.Label != null && p.Label.StartsWith("Oco_")).ToList();
                            foreach(var pos in ocoPositions)
                            {
                                if (!_posAgeBars.ContainsKey(pos.Id)) _posAgeBars[pos.Id] = 0;
                                _posAgeBars[pos.Id]++;
                                
                                int horizon = ExtractHorizon(pos.Label);
                                if (_posAgeBars[pos.Id] >= horizon)
                                {
                                    Print($"[HORIZON EXIT] Closing {pos.Id} after {horizon} bars");
                                    ClosePositionAsync(pos);
                                    _posAgeBars.Remove(pos.Id);
                                }
                            }

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

        private int ExtractHorizon(string label)
        {
            int idx = label.LastIndexOf("|H");
            if (idx != -1)
            {
                if (int.TryParse(label.Substring(idx + 2), out int h)) return h;
            }
            return 6;
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
                    
                    try 
                    {
                        PlaceOcoOrders(pred);
                    }
                    catch (Exception ex)
                    {
                        Print($"[EXEC ERROR] Could not place OCO for {pred.candidate_uid}: {ex.Message}");
                    }
                }
            }
        }

        private void PlaceOcoOrders(OcoPrediction pred)
        {
            double barrierPips = pred.barrier_pips; 
            double volume = Symbol.QuantityToVolumeInUnits(LotSize);
            string groupLabel = $"Oco_{pred.candidate_uid}_{Server.Time:yyyyMMddHHmmss}|H{pred.horizon}";

            double buyPrice = Symbol.Ask + (barrierPips * Symbol.PipSize);
            double sellPrice = Symbol.Bid - (barrierPips * Symbol.PipSize);

            PlaceStopOrderAsync(TradeType.Buy, Symbol.Name, volume, buyPrice, groupLabel);
            PlaceStopOrderAsync(TradeType.Sell, Symbol.Name, volume, sellPrice, groupLabel);
            
            Print($"[OCO PLACED] {groupLabel} | BuyStop: {buyPrice:F4} | SellStop: {sellPrice:F4}");
        }

        protected override void OnPendingOrderFilled(PendingOrderFilledEventArgs args)
        {
            var pos = args.Position;
            if (pos.Label != null && pos.Label.StartsWith("Oco_"))
            {
                // Cancel the opposite leg
                var ordersToCancel = PendingOrders.Where(o => o.Label == pos.Label && o.Id != args.PendingOrder.Id).ToList();
                foreach (var order in ordersToCancel)
                {
                    CancelPendingOrderAsync(order);
                    Print($"[OCO CANCEL] Cancelled opposite leg for {pos.Label}");
                }
                
                // Track touch via API
                TrackTouchAsync(pos.Id.ToString());
            }
        }

        protected override void OnPositionClosed(PositionClosedEventArgs args)
        {
            var pos = args.Position;
            if (pos.Label != null && pos.Label.StartsWith("Oco_"))
            {
                _posAgeBars.Remove(pos.Id);
            }
        }

        private async void TrackTouchAsync(string brokerPosId)
        {
            try {
                var payload = new { symbol = _internalSymbol, broker_pos_id = brokerPosId };
                var json = JsonSerializer.Serialize(payload, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                await _client.PostAsync($"{BaseUrl}/trades/touch", content);
            } catch (Exception ex) {
                Print($"[API ERR] TrackTouchAsync: {ex}");
            }
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
        public int horizon { get; set; }
        public double barrier_pips { get; set; }
        public double cap_pips { get; set; }
        public string threshold_source { get; set; }
        public string model_month { get; set; }
    }
}
