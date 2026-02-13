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
    /// BehemothTradeManager — Multi-pair stat-arb cBot.
    /// Collects 750 bars of close prices for 18 unique symbols,
    /// POSTs them to the Behemoth API which computes Kalman/z-score signals,
    /// then executes trades and processes exit signals.
    /// </summary>
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class BehemothTradeManager : Robot
    {
        [Parameter("API Base URL", DefaultValue = "http://127.0.0.1:8000")]
        public string BaseUrl { get; set; }

        [Parameter("Lot Size", DefaultValue = 0.05, MinValue = 0.01, Step = 0.01)]
        public double LotSize { get; set; }

        [Parameter("Bar Size", DefaultValue = "m15")]
        public string BarSize { get; set; }

        [Parameter("Bar Count", DefaultValue = 1500, MinValue = 800)]
        public int BarCount { get; set; }

        private HttpClient _client;
        private Bars _bars;
        private DateTime _lastProcessedBarTime = DateTime.MinValue;
        private bool _isFirstBar = true;

        protected override void OnStart()
        {
            try
            {
                _client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                
                // Reset API state on start
                ResetAPI();

                var tf = BarSize == "m5" ? TimeFrame.Minute5 : TimeFrame.Minute15;
                _bars = MarketData.GetBars(tf);

                // Build reverse mapping
                foreach (var kvp in SymbolMap)
                    BrokerToInternal[kvp.Value] = kvp.Key;

                // Resolve symbols... (omitted for brevity, keep existing logic if creating partial replacement?)
                // Actually to keep it safe, I should just modify the parts I need.
                // The block below replicates the OnStart logic.
                
                // ... (Load symbols loop) ...
                // Effectively I need to replace OnStart and add ResetAPI.
                // But the user said "do not overreact".
                
                // Let's do this in chunks. Validating OnStart logic.
                // The provided replacement content must be exact.
                
                // I will rewrite OnStart to include ResetAPI() call.
                // And add ResetAPI method below OnStart.
            } 
            catch (Exception ex) 
            { 
                Print($"ERROR in OnStart: {ex}"); 
            }
        }
        
        private void ResetAPI()
        {
            try
            {
                var url = $"{BaseUrl}/reset/{BarSize}";
                var content = new StringContent("", Encoding.UTF8, "application/json");
                var task = _client.PostAsync(url, content);
                task.Wait(TimeSpan.FromSeconds(5));
                if (task.Result.IsSuccessStatusCode)
                    Print("API State Reset Successful");
                else
                    Print($"API Reset Failed: {task.Result.StatusCode}");
            }
            catch (Exception ex)
            {
                Print($"API Reset Exception: {ex.Message}");
            }
        }

        protected override void OnBar()
        {
            var now = Bars.LastBar.OpenTime; // Start of the new bar = End of the confirmed bar?
            // Actually Bars.OpenTimes.Last(0) is the open time of the forming bar.
            // Behemoth trades on COMPLETED bars.
            // OnBar triggers when a bar closes and a new one opens.
            // So 'now' usually refers to the close time of the previous bar / open of new.
            
            // To be consistent with data, we pass the timestamp of the *just closed* bar?
            // Or the current time? 
            // In API: ts = datetime.fromisoformat(body.timestamp)
            // It uses this for logging and cooldown.
            
            // If I just access Bars.Last(1).OpenTime, that is the opened bar that just closed.
            // But let's stick to existing logic for 'now'. 
            // Existing: nothing specific about 'now' creation in the snippet I saw?
            // Ah, OnBar() usually has no args.
            
            // Let's focus on defining 'barsNeeded'
            int barsNeeded = _isFirstBar ? BarCount : 1;
            
            // ── Collect bar data ──
            var barData = CollectBarData(barsNeeded);
            if (barData.Count == 0) return;

            Print($"BAR {_barsProcessed}: Posting {barsNeeded} bar(s) for {barData.Count} symbols...");

            // ── POST ──
            var signalTask = PostBarData(barData, now);
            if (!signalTask.Wait(TimeSpan.FromSeconds(20)))
            {
                Print("TIMEOUT: Signal computation timed out");
                return;
            }

            var response = signalTask.Result;
            if (response == null) return;
            
            // If successful huge payload, switch to incremental
            if (_isFirstBar)
            {
                _isFirstBar = false;
                Print("Switching to INCREMENTAL mode (1 bar updates)");
            }

            // ... (Process Exits/Signals) ...
            // I need to be careful replacing the whole OnBar.
            // I will use multiple Replace calls to avoid breaking the file.
            // Changing OnBar signature or body? existing is just OnBar().
        }
        // API uses the left side, cTrader uses the right side
        private static readonly Dictionary<string, string> SymbolMap = new Dictionary<string, string>
        {
            // FX — same names
            { "EURUSD", "EURUSD" },
            { "GBPUSD", "GBPUSD" },
            { "AUDUSD", "AUDUSD" },
            { "NZDUSD", "NZDUSD" },
            { "USDCAD", "USDCAD" },
            { "USDCHF", "USDCHF" },
            { "USDJPY", "USDJPY" },
            // Metals — same names
            { "XAUUSD", "XAUUSD" },
            { "XAGUSD", "XAGUSD" },
            // Energy — broker uses XBRUSD for Brent
            { "BCOUSD", "XBRUSD" },
        };

        // Reverse mapping: broker name → internal API name
        private static readonly Dictionary<string, string> BrokerToInternal = new Dictionary<string, string>();

        // Resolved Bars objects keyed by INTERNAL name (for API payload)
        private Dictionary<string, Bars> _symbolBars = new Dictionary<string, Bars>();

        private static readonly JsonSerializerOptions _jsonOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        // ── Lifecycle ──────────────────────────────────────────────────

        protected override void OnStart()
        {
            try
            {
                _client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                var tf = BarSize == "m5" ? TimeFrame.Minute5 : TimeFrame.Minute15;
                _bars = MarketData.GetBars(tf);

                // Build reverse mapping
                foreach (var kvp in SymbolMap)
                    BrokerToInternal[kvp.Value] = kvp.Key;

                // Resolve all 18 symbols using broker names, store keyed by internal name
                int loaded = 0;
                foreach (var kvp in SymbolMap)
                {
                    var internalName = kvp.Key;
                    var brokerName = kvp.Value;
                    try
                    {
                        var sym = Symbols.GetSymbol(brokerName);
                        if (sym != null)
                        {
                            var bars = MarketData.GetBars(tf, brokerName);
                            if (bars != null && bars.Count > 0)
                            {
                                // Load enough historical bars for the lookback window
                                while (bars.Count < BarCount)
                                {
                                    int before = bars.Count;
                                    bars.LoadMoreHistory();
                                    if (bars.Count == before) break; // No more history available
                                }
                                _symbolBars[internalName] = bars;
                                loaded++;
                                Print($"Loaded {brokerName} → {internalName} ({bars.Count} bars)");
                                Print($"  SPEC: MinVol={sym.VolumeInUnitsMin} Step={sym.VolumeInUnitsStep} LotSize={sym.LotSize} Bid={sym.Bid:F4}");
                            }
                            else
                            {
                                Print($"WARN: No bars for {brokerName} ({internalName})");
                            }
                        }
                        else
                        {
                            Print($"WARN: Symbol {brokerName} not found in cTrader");
                        }
                    }
                    catch (Exception ex)
                    {
                        Print($"WARN: Failed to load {brokerName}: {ex.Message}");
                    }
                }

                Print($"BehemothTradeManager started — API: {BaseUrl}, Bar: {BarSize}, Lot: {LotSize}, Symbols: {loaded}/{SymbolMap.Count}");
            }
            catch (Exception ex)
            {
                Print($"ERROR in OnStart: {ex}");
            }
        }

        protected override void OnBar()
        {
            try
            {
                var lastCompletedBarTime = _bars.OpenTimes[_bars.Count - 2];
                if (lastCompletedBarTime <= _lastProcessedBarTime)
                    return;

                _barsProcessed++;
                _lastProcessedBarTime = lastCompletedBarTime;
                var now = Server.Time;

                // ── Friday protection ──
                if (now.DayOfWeek == DayOfWeek.Friday)
                {
                    if (now.Hour >= 21 && now.Minute >= 45)
                    {
                        foreach (var pos in Positions.Where(p => p.Label != null && p.Label.StartsWith("Bhm_")))
                        {
                            Print($"FRIDAY_CLOSE: {pos.Label}");
                            var closeOk = ClosePosition(pos);
                            if (closeOk.IsSuccessful)
                                NotifyClose(pos);
                        }
                        return;
                    }
                    if (now.Hour >= 20)
                    {
                        Print("FRIDAY CUTOFF: Skipping signal poll after 20:00 UTC");
                        return;
                    }
                }

                // ── Collect bar data from all symbols ──
                var barData = CollectBarData();
                if (barData.Count == 0)
                {
                    Print($"BAR {_barsProcessed}: No bar data collected");
                    return;
                }

                Print($"BAR {_barsProcessed}: Collected {barData.Count} symbols, posting to API...");

                // ── POST bar data to API ──
                var signalTask = PostBarData(barData, now);
                if (!signalTask.Wait(TimeSpan.FromSeconds(20)))
                {
                    Print("TIMEOUT: Signal computation timed out");
                    return;
                }

                var response = signalTask.Result;
                if (response == null)
                {
                    Print($"BAR {_barsProcessed}: No response from API");
                    return;
                }

                // ── Process exit signals first ──
                if (response.exits != null && response.exits.Count > 0)
                {
                    Print($"BAR {_barsProcessed}: {response.exits.Count} exit signal(s)");
                    foreach (var exit in response.exits)
                    {
                        ProcessExit(exit, now);
                    }
                }

                // ── Process entry signals ──
                if (response.signals != null && response.signals.Count > 0)
                {
                    Print($"BAR {_barsProcessed}: {response.signals.Count} entry signal(s)");
                    foreach (var sig in response.signals)
                    {
                        ProcessSignal(sig, now);
                    }
                }

                if ((response.signals == null || response.signals.Count == 0)
                    && (response.exits == null || response.exits.Count == 0))
                {
                    Print($"BAR {_barsProcessed}: No signals or exits");
                }
            }
            catch (Exception ex)
            {
                Print($"ERROR in OnBar: {ex.InnerException?.Message ?? ex.Message}");
            }
        }

        protected override void OnStop()
        {
            _client?.Dispose();
        }

        // ── Bar Data Collection ────────────────────────────────────────

        // ── Bar Data Collection ────────────────────────────────────────

        private Dictionary<string, List<double>> CollectBarData(int count)
        {
            var result = new Dictionary<string, List<double>>();

            foreach (var kvp in _symbolBars)
            {
                var symName = kvp.Key;
                var bars = kvp.Value;

                // Ensure we have enough bars
                if (bars.Count < count + 1)
                {
                    // For incremental (count=1), we need at least 2 bars (1 closed, 1 developing)
                    // For init (count=1500), we need 1501
                    if (_isFirstBar)
                        Print($"WARN: Only {bars.Count} bars for {symName}, skipping");
                    continue;
                }

                var closes = new List<double>(count);
                // bars.Count - 1 is the index of the last CLOSED bar
                // We want 'count' bars ending at index (bars.Count - 1)
                int startIdx = bars.Count - 1 - count + 1; 
                // Wait: 
                // Index: 0 1 2 3 [4] (developing)
                // Count=5. Last closed is 3.
                // We want 1 bar? Index 3.
                // Start = 5 - 1 - 1 + 1 = 4? No.
                
                // Last closed index = bars.Count - 2 (in 0-cAlgo index? No, Bars array 0..Count-1)
                // bars.LastBar is the developing bar (index Count-1).
                // bars.Last(1) is the last closed bar (index Count-2).
                
                // Let's us cAlgo API indices.
                // index 0 is oldest. index Count-1 is newest (developing).
                
                int lastClosedIndex = bars.Count - 2;
                if (lastClosedIndex < 0) continue;
                
                int firstIndex = lastClosedIndex - count + 1;
                if (firstIndex < 0) firstIndex = 0; // Should be handled by check above
                
                for (int i = firstIndex; i <= lastClosedIndex; i++)
                {
                    closes.Add(bars.ClosePrices[i]);
                }

                result[symName] = closes;
            }

            return result;
        }

        // ── Signal Fetching via POST ───────────────────────────────────

        private async Task<SignalsResponse> PostBarData(
            Dictionary<string, List<double>> barData, DateTime currentTime)
        {
            try
            {
                var payload = new
                {
                    bars = barData,
                    current_time = currentTime.ToUniversalTime().ToString("O"),
                    equity = Account.Equity
                };

                var json = JsonSerializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var url = $"{BaseUrl}/signals/{BarSize}";
                Print($"POST {url} ({json.Length / 1024}KB)");

                var resp = await _client.PostAsync(url, content);
                
                // Self-Healing: If API lost state (409), force full resend next time
                if (resp.StatusCode == System.Net.HttpStatusCode.Conflict)
                {
                    Print("API STATE MISSING (409): Triggering FULL HISTORY RESEND on next tick.");
                    _isFirstBar = true;
                    return null;
                }

                if (!resp.IsSuccessStatusCode)
                {
                    var errBody = await resp.Content.ReadAsStringAsync();
                    Print($"API Error: {resp.StatusCode} — {errBody}");
                    return null;
                }

                var body = await resp.Content.ReadAsStringAsync();
                return JsonSerializer.Deserialize<SignalsResponse>(body, _jsonOpts);
            }
            catch (Exception ex)
            {
                Print($"EXCEPTION in PostBarData: {ex.Message}");
                return null;
            }
        }

        // ── Exit Processing ────────────────────────────────────────────

        private void ProcessExit(ExitSignal exit, DateTime now)
        {
            var ctraderPos = Positions.FirstOrDefault(p =>
                p.Label != null && p.Label.Contains($"|{exit.position_id}"));

            if (ctraderPos == null)
            {
                Print($"EXIT_SKIP: No cTrader position for API id={exit.position_id?.Substring(0, 8)}");
                return;
            }

            var reason = exit.reason ?? "UNKNOWN";
            var zStr = exit.z_score.HasValue ? $"z={exit.z_score:F2}" : "z=N/A";
            Print($"EXIT_{reason}: {exit.pair} {exit.side} ({zStr}, bars={exit.bars_held})");

            var closeResult = ClosePosition(ctraderPos);
            if (closeResult.IsSuccessful)
            {
                NotifyClose(ctraderPos);
                Print($"EXIT_CLOSED: {ctraderPos.Label}");
            }
            else
            {
                Print($"EXIT_FAILED: {ctraderPos.Label} — {closeResult.Error}");
            }
        }

        // ── Entry Signal Processing ────────────────────────────────────

        private void ProcessSignal(SignalInfo sig, DateTime now)
        {
            // API returns internal names (e.g. SPXUSD), translate to broker names (e.g. US 500)
            string internalSymbol = sig.active_leg == "X" ? sig.leg_x : sig.leg_y;
            string tradeSymbol = SymbolMap.ContainsKey(internalSymbol) ? SymbolMap[internalSymbol] : internalSymbol;
            string label = $"Bhm_{sig.pair}_{sig.side}";

            var existingPos = Positions.FirstOrDefault(p => p.Label != null && p.Label.StartsWith(label));
            if (existingPos != null)
            {
                Print($"SKIP: Position already open for {label}");
                return;
            }

            var existingOrder = PendingOrders.FirstOrDefault(o => o.Label != null && o.Label.StartsWith(label));
            if (existingOrder != null)
            {
                Print($"SKIP: Pending order exists for {label}");
                return;
            }

            var sym = Symbols.GetSymbol(tradeSymbol);
            if (sym == null)
            {
                Print($"SKIP: Symbol {tradeSymbol} not found in cTrader");
                return;
            }

            // Calculate Volume & Notional *before* creating API position
            double volume;
            double notionalUSD;
            double price = sym.Bid;

            if (sig.TargetUsd > 0)
            {
                Print($"DEBUG-SIZE: {sig.pair} Target=${sig.TargetUsd:F0} Price={price:F4}");
                // Notional-Based Sizing: volume = target_usd / price
                double rawVolume = sig.TargetUsd / price;
                volume = sym.NormalizeVolumeInUnits(rawVolume, RoundingMode.ToNearest);
                if (volume < sym.VolumeInUnitsMin) volume = sym.VolumeInUnitsMin;
                notionalUSD = volume * price;
            }
            else
            {
                Print($"DEBUG-SIZE: {sig.pair} Target=0 (Fallback to LotSize)");
                // Fallback to fixed LotSize
                var lotSize = sig.LotSize > 0 ? sig.LotSize : LotSize;
                volume = sym.QuantityToVolumeInUnits(lotSize);
                // Approx notional for reporting (assuming USD base or close enough)
                notionalUSD = volume * price;
            }

            var positionId = CreatePosition(sig, now, notionalUSD);
            if (string.IsNullOrEmpty(positionId))
            {
                Print($"SKIP: API rejected position for {sig.pair}");
                return;
            }
            
            var tradeType = sig.side == "LONG" ? TradeType.Buy : TradeType.Sell;
            string fullLabel = $"Bhm_{sig.pair}_{sig.side}|{positionId}";

            var result = ExecuteMarketOrder(tradeType, tradeSymbol, volume, fullLabel);
            if (result.IsSuccessful)
            {
                Print($"OPENED: {fullLabel} @ {result.Position.EntryPrice:F5} (z={sig.z_score:F2}, ${notionalUSD:F0})");
                NotifyOpen(positionId, result.Position.EntryPrice, now);
            }
            else
            {
                Print($"ORDER FAILED: {fullLabel} — {result.Error}");
                CancelPosition(positionId);
            }
        }

        // ── API Position Lifecycle ─────────────────────────────────────

        private string CreatePosition(SignalInfo sig, DateTime now, double notionalUSD)
        {
            try
            {
                var payload = new
                {
                    strategy_id = $"mom_{BarSize}",
                    pair = sig.pair,
                    side = sig.side,
                    active_leg = sig.active_leg,
                    size = notionalUSD,
                    entry_ts = now.ToUniversalTime().ToString("O"),
                    metadata = new { bar = BarSize, z_score = sig.z_score, beta = sig.beta }
                };

                var json = JsonSerializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var idempotencyKey = $"mom_{BarSize}:{sig.pair}:{now:yyyyMMddHHmm}";
                var request = new HttpRequestMessage(System.Net.Http.HttpMethod.Post, $"{BaseUrl}/positions")
                {
                    Content = content
                };
                request.Headers.Add("Idempotency-Key", idempotencyKey);

                var task = _client.SendAsync(request);
                if (!task.Wait(TimeSpan.FromSeconds(5)))
                    return null;

                var resp = task.Result;
                if (!resp.IsSuccessStatusCode)
                {
                    var errBody = resp.Content.ReadAsStringAsync().Result;
                    Print($"CREATE REJECTED ({resp.StatusCode}): {errBody}");
                    return null;
                }

                var body = resp.Content.ReadAsStringAsync().Result;
                var result = JsonSerializer.Deserialize<PositionApiResponse>(body, _jsonOpts);
                return result?.id;
            }
            catch (Exception ex)
            {
                Print($"EXCEPTION in CreatePosition: {ex.Message}");
                return null;
            }
        }

        private void NotifyOpen(string positionId, double entryPrice, DateTime now)
        {
            try
            {
                var payload = new
                {
                    entry_price = entryPrice,
                    entry_ts = now.ToUniversalTime().ToString("O")
                };
                var json = JsonSerializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var task = _client.PostAsync($"{BaseUrl}/positions/{positionId}/open", content);
                task.Wait(TimeSpan.FromSeconds(3));
            }
            catch (Exception ex)
            {
                Print($"WARN: NotifyOpen failed: {ex.Message}");
            }
        }

        private void NotifyClose(Position pos)
        {
            try
            {
                var parts = pos.Label?.Split('|');
                if (parts == null || parts.Length < 2) return;
                var positionId = parts[1];

                var pnlBps = (pos.NetProfit / (LotSize * 100000)) * 10000;

                var payload = new
                {
                    exit_price = pos.EntryPrice + (pos.NetProfit / (pos.VolumeInUnits * pos.Symbol.PipSize / pos.Symbol.PipValue)),
                    exit_ts = Server.Time.ToUniversalTime().ToString("O"),
                    pnl_bps = pnlBps
                };
                var json = JsonSerializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var task = _client.PostAsync($"{BaseUrl}/positions/{positionId}/close", content);
                task.Wait(TimeSpan.FromSeconds(3));
            }
            catch (Exception ex)
            {
                Print($"WARN: NotifyClose failed: {ex.Message}");
            }
        }

        private void CancelPosition(string positionId)
        {
            try
            {
                var task = _client.PostAsync($"{BaseUrl}/positions/{positionId}/cancel", null);
                task.Wait(TimeSpan.FromSeconds(3));
            }
            catch { }
        }
    }

    // ── JSON Response Models ───────────────────────────────────────────

    public class SignalsResponse
    {
        public string bar { get; set; }
        public List<SignalInfo> signals { get; set; }
        public List<ExitSignal> exits { get; set; }
        public int checked_pairs { get; set; }
        public string timestamp { get; set; }
    }

    public class SignalInfo
    {
        public string pair { get; set; }
        public string side { get; set; }
        public string active_leg { get; set; }
        public double z_score { get; set; }
        public double beta { get; set; }
        public string leg_x { get; set; }
        public string leg_y { get; set; }
        [JsonPropertyName("lot_size")]
        public double LotSize { get; set; }

        [JsonPropertyName("target_usd")]
        public double TargetUsd { get; set; }
    }

    public class ExitSignal
    {
        public string position_id { get; set; }
        public string pair { get; set; }
        public string side { get; set; }
        public string reason { get; set; }
        public double? z_score { get; set; }
        public int? bars_held { get; set; }
    }

    public class PositionApiResponse
    {
        public string id { get; set; }
        public string status { get; set; }
    }
}
