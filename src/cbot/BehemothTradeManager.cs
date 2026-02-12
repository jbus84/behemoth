using System;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
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
        private int _barsProcessed = 0;

        // Mapping: internal API name → broker cTrader symbol name
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
            // Indices — broker uses descriptive names
            { "SPXUSD", "US 500" },
            { "UDXUSD", "US 30" },
            { "NSXUSD", "US TECH 100" },
            { "GRXEUR", "GERMANY 40" },
            { "FRXEUR", "FRANCE 40" },
            { "UKXGBP", "UK 100" },
            { "JPXJPY", "JAPAN 225" },
            { "HKXHKD", "HONG KONG 50" },
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

        private Dictionary<string, List<double>> CollectBarData()
        {
            var result = new Dictionary<string, List<double>>();

            foreach (var kvp in _symbolBars)
            {
                var symName = kvp.Key;
                var bars = kvp.Value;

                int count = Math.Min(BarCount, bars.Count - 1);  // Exclude current incomplete bar
                if (count < 100)
                {
                    Print($"WARN: Only {count} bars for {symName}, skipping");
                    continue;
                }

                var closes = new List<double>(count);
                int startIdx = bars.Count - 1 - count;  // Skip last (incomplete) bar
                for (int i = startIdx; i < bars.Count - 1; i++)
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

            if (sig.target_usd > 0)
            {
                // Notional-Based Sizing: volume = target_usd / price
                double rawVolume = sig.target_usd / price;
                volume = sym.NormalizeVolumeInUnits(rawVolume, RoundingMode.ToNearest);
                if (volume < sym.VolumeInUnitsMin) volume = sym.VolumeInUnitsMin;
                notionalUSD = volume * price;
            }
            else
            {
                // Fallback to fixed LotSize
                var lotSize = sig.lot_size > 0 ? sig.lot_size : LotSize;
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
        public double lot_size { get; set; }
        public double target_usd { get; set; }
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
