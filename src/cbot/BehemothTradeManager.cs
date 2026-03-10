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
    /// for state warmup. Then streams live ticks (single or batched) and triggers predictions.
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

        [Parameter("Enable FTMO Guards", DefaultValue = true)]
        public bool EnableFtmoGuards { get; set; }

        [Parameter("FTMO Profile ID", DefaultValue = "ftmo_10k_challenge_2step")]
        public string FtmoProfileId { get; set; }

        [Parameter("Hard Stop On Risk Block", DefaultValue = true)]
        public bool HardStopOnRiskBlock { get; set; }

        [Parameter("Enable Tick Batch", DefaultValue = true)]
        public bool EnableTickBatch { get; set; }

        [Parameter("Tick Batch Size", DefaultValue = 20, MinValue = 1, MaxValue = 100)]
        public int TickBatchSize { get; set; }

        [Parameter("Tick Flush Ms", DefaultValue = 100, MinValue = 1, MaxValue = 2000)]
        public int TickFlushMs { get; set; }

        [Parameter("Tick Queue Cap", DefaultValue = 20000, MinValue = 1000, MaxValue = 200000)]
        public int TickQueueCap { get; set; }

        private HttpClient _client;
        private Ticks _historicalTicks;
        private static readonly HashSet<string> ActiveSymbols = new HashSet<string>
        {
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "USDCHF",
            "AUDUSD",
            "USDCAD",
        };

        private string GetInternalSymbolName(string brokerName)
        {
            if (string.IsNullOrWhiteSpace(brokerName))
            {
                return brokerName;
            }

            string raw = brokerName.Trim().ToUpperInvariant();
            string lettersOnly = new string(raw.Where(char.IsLetter).ToArray());
            if (lettersOnly.Length >= 6)
            {
                string canonical = lettersOnly.Substring(0, 6);
                if (ActiveSymbols.Contains(canonical))
                {
                    return canonical;
                }
            }

            if (raw.Length >= 6)
            {
                string prefix = raw.Substring(0, 6);
                if (ActiveSymbols.Contains(prefix))
                {
                    return prefix;
                }
            }

            return raw;
        }

        private static readonly JsonSerializerOptions _jsonOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        private string _internalSymbol;
        private Dictionary<int, int> _posAgeBars = new Dictionary<int, int>();
        private int _consecutiveTickIngestFailures = 0;
        private int _consecutivePredictFailures = 0;
        private bool _tickFeedHealthy = true;
        private bool _predictPathHealthy = true;
        private const int MaxConsecutiveTickIngestFailures = 20;
        private const int MaxConsecutivePredictFailures = 5;
        private readonly List<TickPayload> _tickQueue = new List<TickPayload>();
        private long _clientTickSeq = 0;
        private DateTime _lastTickFlushUtc = DateTime.MinValue;

        protected override void OnStart()
        {
            try
            {
                _client = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
                _internalSymbol = GetInternalSymbolName(Symbol.Name);
                _lastTickFlushUtc = Server.Time.ToUniversalTime();
                PendingOrders.Filled += OnPendingOrderFilled;
                Positions.Closed += OnPositionClosed;
                
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

                if (EnableFtmoGuards)
                {
                    SubmitFtmoSnapshot();
                }
                
                RecoverActiveTradesAsync();
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
                var nowUtc = now.ToUniversalTime();

                bool skipPrediction = false;
                // Friday protection
                if (now.DayOfWeek == DayOfWeek.Friday)
                {
                    if (now.Hour >= 21 && now.Minute >= 45)
                    {
                        foreach (var pos in Positions.Where(p => p.SymbolName == Symbol.Name && p.Label != null && p.Label.StartsWith("Oco_")))
                        {
                            var closeOk = ClosePosition(pos);
                        }
                    }
                    if (now.Hour >= 20)
                    {
                        skipPrediction = true;
                    }
                }

                var tick = new TickPayload
                {
                    symbol = _internalSymbol,
                    timestamp = nowUtc.ToString("O"),
                    bid = Symbol.Bid,
                    ask = Symbol.Ask,
                    tick_volume = 1.0,
                    client_tick_seq = ++_clientTickSeq,
                };
                _tickQueue.Add(tick);

                if (_tickQueue.Count > TickQueueCap)
                {
                    int dropCount = _tickQueue.Count - TickQueueCap;
                    _tickQueue.RemoveRange(0, dropCount);
                    RegisterTickIngestFailure("queue_overflow_drop");
                    Print($"[TICK QUEUE] overflow drop={dropCount} cap={TickQueueCap}");
                }

                bool shouldFlush = false;
                if (EnableTickBatch)
                {
                    shouldFlush = _tickQueue.Count >= TickBatchSize
                        || (nowUtc - _lastTickFlushUtc).TotalMilliseconds >= TickFlushMs;
                    if (shouldFlush)
                    {
                        FlushTickQueue(skipPrediction);
                    }
                }
                else
                {
                    FlushTickQueue(skipPrediction);
                }
            }
            catch (Exception ex)
            {
                RegisterTickIngestFailure("exception");
                Print($"[WARN] OnTick fast-fail: {ex.Message}");
            }
        }

        private void FlushTickQueue(bool skipPrediction)
        {
            if (_tickQueue.Count <= 0)
            {
                return;
            }

            int chunkSize = EnableTickBatch ? Math.Max(1, TickBatchSize) : 1;
            while (_tickQueue.Count > 0)
            {
                int take = Math.Min(chunkSize, _tickQueue.Count);
                var chunk = _tickQueue.Take(take).ToList();
                bool posted = EnableTickBatch
                    ? TryPostTickBatch(chunk, skipPrediction)
                    : TryPostSingleTick(chunk[0], skipPrediction);
                if (!posted)
                {
                    return;
                }
                _tickQueue.RemoveRange(0, take);
                _lastTickFlushUtc = Server.Time.ToUniversalTime();

                if (!EnableTickBatch || _tickQueue.Count < chunkSize)
                {
                    return;
                }
            }
        }

        private bool TryPostSingleTick(TickPayload tick, bool skipPrediction)
        {
            try
            {
                var json = JsonSerializer.Serialize(tick, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var task = _client.PostAsync($"{BaseUrl}/ticks", content);
                if (!task.Wait(TimeSpan.FromSeconds(2)))
                {
                    RegisterTickIngestFailure("timeout");
                    Print("[TICK ERROR] /ticks timeout");
                    return false;
                }

                var resp = task.Result;
                var body = resp.Content.ReadAsStringAsync().Result;
                if (!resp.IsSuccessStatusCode)
                {
                    RegisterTickIngestFailure($"http_{(int)resp.StatusCode}");
                    Print($"[TICK ERROR] {resp.StatusCode} body={body}");
                    return false;
                }

                var tickResp = JsonSerializer.Deserialize<TickResponse>(body, _jsonOpts);
                if (tickResp == null)
                {
                    RegisterTickIngestFailure("malformed_response");
                    Print("[TICK ERROR] malformed response from /ticks");
                    return false;
                }

                if (!tickResp.tick_accepted)
                {
                    string reason = string.IsNullOrWhiteSpace(tickResp.drop_reason) ? "rejected" : tickResp.drop_reason;
                    RegisterTickIngestFailure(reason);
                    Print($"[TICK DROP] reason={reason} seq={tickResp.symbol_tick_seq}");
                    return true;
                }

                RegisterTickIngestSuccess();
                if (tickResp.bar_completed)
                {
                    HandleCompletedBars(tickResp.completed_bar_ticks ?? new List<int>(), skipPrediction);
                }
                return true;
            }
            catch (Exception ex)
            {
                RegisterTickIngestFailure("exception");
                Print($"[TICK ERROR] /ticks exception: {ex.Message}");
                return false;
            }
        }

        private bool TryPostTickBatch(List<TickPayload> chunk, bool skipPrediction)
        {
            try
            {
                var payload = new
                {
                    symbol = _internalSymbol,
                    ticks = chunk,
                };
                var json = JsonSerializer.Serialize(payload, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var task = _client.PostAsync($"{BaseUrl}/ticks/batch", content);
                if (!task.Wait(TimeSpan.FromSeconds(3)))
                {
                    RegisterTickIngestFailure("batch_timeout");
                    Print($"[TICK BATCH ERROR] timeout size={chunk.Count}");
                    return false;
                }

                var resp = task.Result;
                var body = resp.Content.ReadAsStringAsync().Result;
                if (!resp.IsSuccessStatusCode)
                {
                    RegisterTickIngestFailure($"batch_http_{(int)resp.StatusCode}");
                    Print($"[TICK BATCH ERROR] {resp.StatusCode} body={body}");
                    return false;
                }

                var outBody = JsonSerializer.Deserialize<TickBatchResponse>(body, _jsonOpts);
                if (outBody == null)
                {
                    RegisterTickIngestFailure("batch_malformed_response");
                    Print("[TICK BATCH ERROR] malformed response");
                    return false;
                }

                if (outBody.accepted_count > 0)
                {
                    RegisterTickIngestSuccess();
                }
                else if (outBody.dropped_count > 0)
                {
                    RegisterTickIngestFailure("batch_all_dropped");
                }

                if (outBody.bar_completed && outBody.completed_bar_ticks != null && outBody.completed_bar_ticks.Count > 0)
                {
                    HandleCompletedBars(outBody.completed_bar_ticks, skipPrediction);
                }
                return true;
            }
            catch (Exception ex)
            {
                RegisterTickIngestFailure("batch_exception");
                Print($"[TICK BATCH ERROR] exception: {ex.Message}");
                return false;
            }
        }

        private void HandleCompletedBars(List<int> completedBarTicks, bool skipPrediction)
        {
            if (completedBarTicks == null || completedBarTicks.Count == 0)
            {
                return;
            }

            var validTicks = completedBarTicks.Where(x => x > 0).ToList();
            if (validTicks.Count == 0)
            {
                return;
            }

            var barCounts = validTicks
                .GroupBy(x => x)
                .ToDictionary(g => g.Key, g => g.Count());
            var tickSummary = string.Join(",", barCounts.OrderBy(kv => kv.Key).Select(kv => $"{kv.Key}x{kv.Value}"));
            Print($"[BAR COMPLETED] ticks={tickSummary}");

            var ocoPositions = Positions.Where(p => p.SymbolName == Symbol.Name && p.Label != null && p.Label.StartsWith("Oco_")).ToList();
            foreach (var pos in ocoPositions)
            {
                int posBarTicks = ExtractBarTicks(pos.Label);
                if (!barCounts.TryGetValue(posBarTicks, out int completedCount) || completedCount <= 0)
                {
                    continue;
                }
                if (!_posAgeBars.ContainsKey(pos.Id))
                {
                    _posAgeBars[pos.Id] = 0;
                }
                _posAgeBars[pos.Id] += completedCount;

                int horizon = ExtractHorizon(pos.Label);
                if (_posAgeBars[pos.Id] >= horizon)
                {
                    Print($"[HORIZON EXIT] Closing {pos.Id} after {horizon} bars ({posBarTicks}-tick)");
                    ClosePositionAsync(pos);
                    _posAgeBars.Remove(pos.Id);
                }
            }

            if (skipPrediction)
            {
                return;
            }

            if (IsTradingBlockedByRuntimeGuard())
            {
                Print($"[RUNTIME GUARD] Trading blocked: {CurrentRuntimeGuardReason()}");
                return;
            }
            if (EnableFtmoGuards)
            {
                SubmitFtmoSnapshot();
            }

            var uniqueTicks = barCounts.Keys.OrderBy(x => x).ToList();
            if (validTicks.Count != uniqueTicks.Count)
            {
                Print($"[WARN] Multiple bar completions detected in one flush: total={validTicks.Count} unique={uniqueTicks.Count}");
            }
            TriggerPrediction(uniqueTicks);
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

        private int ExtractBarTicks(string label)
        {
            int tIdx = label.IndexOf("|T");
            int hIdx = label.IndexOf("|H");
            if (tIdx != -1 && hIdx != -1 && hIdx > tIdx)
            {
                int len = hIdx - (tIdx + 2);
                if (int.TryParse(label.Substring(tIdx + 2, len), out int bt)) return bt;
            }
            return 100; // Default fallback
        }

        private bool IsTradingBlockedByRuntimeGuard()
        {
            return !_tickFeedHealthy || !_predictPathHealthy;
        }

        private string CurrentRuntimeGuardReason()
        {
            if (!_tickFeedHealthy) return "tick_ingest_unhealthy";
            if (!_predictPathHealthy) return "predict_path_unhealthy";
            return "none";
        }

        private void RegisterTickIngestFailure(string reason)
        {
            _consecutiveTickIngestFailures++;
            if (_consecutiveTickIngestFailures >= MaxConsecutiveTickIngestFailures && _tickFeedHealthy)
            {
                _tickFeedHealthy = false;
                Print($"[RUNTIME GUARD] Tick ingest unhealthy; blocking new entries. reason={reason} failures={_consecutiveTickIngestFailures}");
            }
        }

        private void RegisterTickIngestSuccess()
        {
            _consecutiveTickIngestFailures = 0;
            if (!_tickFeedHealthy)
            {
                _tickFeedHealthy = true;
                Print("[RUNTIME GUARD] Tick ingest recovered; entry block cleared.");
            }
        }

        private void RegisterPredictFailure(string reason)
        {
            _consecutivePredictFailures++;
            if (_consecutivePredictFailures >= MaxConsecutivePredictFailures && _predictPathHealthy)
            {
                _predictPathHealthy = false;
                Print($"[RUNTIME GUARD] Predict path unhealthy; blocking new entries. reason={reason} failures={_consecutivePredictFailures}");
            }
        }

        private void RegisterPredictSuccess()
        {
            _consecutivePredictFailures = 0;
            if (!_predictPathHealthy)
            {
                _predictPathHealthy = true;
                Print("[RUNTIME GUARD] Predict path recovered; entry block cleared.");
            }
        }

        private void TriggerPrediction(List<int> completedBarTicks)
        {
            try
            {
                string completedTicksTxt = (completedBarTicks == null || completedBarTicks.Count == 0)
                    ? "none"
                    : string.Join(",", completedBarTicks.Distinct().OrderBy(x => x));

                if (EnableFtmoGuards && HardStopOnRiskBlock && !CheckFtmoStatus())
                {
                    Print("[FTMO BLOCK] Account-level guard blocked trading; skipping /predict cycle.");
                    return;
                }

                double volumeUnits = Symbol.QuantityToVolumeInUnits(LotSize);
                var payload = new
                {
                    symbol = _internalSymbol,
                    ftmo_enabled_override = EnableFtmoGuards,
                    requested_volume_units = volumeUnits,
                    requested_lot_size = LotSize,
                    completed_bar_ticks = completedBarTicks ?? new List<int>()
                };
                Print($"[PREDICT] completed_bar_ticks={completedTicksTxt}");
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
                            RegisterPredictSuccess();
                            ProcessPredictions(predictions);
                        }
                        else
                        {
                            RegisterPredictFailure("malformed_response");
                            Print("[PREDICT ERROR] malformed response body");
                        }
                    }
                    else
                    {
                        var body = resp.Content.ReadAsStringAsync().Result;
                        RegisterPredictFailure($"http_{(int)resp.StatusCode}");
                        Print($"[PREDICT ERROR] {resp.StatusCode} body={body}");
                    }
                }
                else
                {
                    RegisterPredictFailure("timeout");
                    Print("[PREDICT ERROR] timeout");
                }
            }
            catch (Exception ex)
            {
                RegisterPredictFailure("exception");
                Print($"[ERROR] TriggerPrediction failed: {ex.Message}");
            }
        }

        private void ProcessPredictions(List<OcoPrediction> predictions)
        {
            foreach (var pred in predictions)
            {
                if (EnableFtmoGuards && pred.risk_blocked)
                {
                    Print($"[FTMO BLOCK] {pred.candidate_uid} blocked: {pred.risk_block_reason}");
                    continue;
                }
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

        private bool SubmitFtmoSnapshot()
        {
            try
            {
                var payload = new
                {
                    symbol = _internalSymbol,
                    balance = Account.Balance,
                    equity = Account.Equity,
                    snapshot_ts = Server.Time.ToUniversalTime().ToString("O")
                };
                var json = JsonSerializer.Serialize(payload, _jsonOpts);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                var task = _client.PostAsync($"{BaseUrl}/risk/ftmo/snapshot", content);
                if (!task.Wait(TimeSpan.FromSeconds(2)))
                {
                    Print("[FTMO SNAPSHOT] Timeout");
                    return false;
                }
                if (!task.Result.IsSuccessStatusCode)
                {
                    Print($"[FTMO SNAPSHOT] API rejected snapshot: {task.Result.StatusCode}");
                    return false;
                }
                return true;
            }
            catch (Exception ex)
            {
                Print($"[FTMO SNAPSHOT ERR] {ex.Message}");
                return false;
            }
        }

        private bool CheckFtmoStatus()
        {
            try
            {
                var statusTask = _client.GetAsync($"{BaseUrl}/risk/ftmo/status?symbol={_internalSymbol}");
                if (!statusTask.Wait(TimeSpan.FromSeconds(2)))
                {
                    Print("[FTMO STATUS] Timeout");
                    return !HardStopOnRiskBlock;
                }
                var resp = statusTask.Result;
                if (!resp.IsSuccessStatusCode)
                {
                    Print($"[FTMO STATUS] API error: {resp.StatusCode}");
                    return !HardStopOnRiskBlock;
                }
                var body = resp.Content.ReadAsStringAsync().Result;
                var status = JsonSerializer.Deserialize<FtmoStatusDTO>(body, _jsonOpts);
                if (status == null)
                {
                    Print("[FTMO STATUS] Invalid payload.");
                    return !HardStopOnRiskBlock;
                }
                if (!string.IsNullOrWhiteSpace(status.profile_id) && !string.IsNullOrWhiteSpace(FtmoProfileId))
                {
                    if (!string.Equals(status.profile_id, FtmoProfileId, StringComparison.OrdinalIgnoreCase))
                    {
                        Print($"[FTMO STATUS] Profile mismatch: API={status.profile_id}, cBot={FtmoProfileId}");
                    }
                }
                if (!status.allow_trading)
                {
                    Print($"[FTMO STATUS] Trading blocked: {status.block_reason}");
                }
                return status.allow_trading;
            }
            catch (Exception ex)
            {
                Print($"[FTMO STATUS ERR] {ex.Message}");
                return !HardStopOnRiskBlock;
            }
        }

        private void PlaceOcoOrders(OcoPrediction pred)
        {
            double barrierPips = pred.barrier_pips; 
            double volume = Symbol.QuantityToVolumeInUnits(LotSize);
            string rid = string.IsNullOrWhiteSpace(pred.risk_reservation_id) ? "NA" : pred.risk_reservation_id;
            string groupLabel = $"Oco_{pred.candidate_uid}_{Server.Time:yyyyMMddHHmmss}|RID{rid}|T{pred.bar_ticks}|H{pred.horizon}";

            double buyPrice = Symbol.Ask + (barrierPips * Symbol.PipSize);
            double sellPrice = Symbol.Bid - (barrierPips * Symbol.PipSize);
            double stopLimitRangePips = pred.cap_pips;

            PlaceStopLimitOrderAsync(TradeType.Buy, Symbol.Name, volume, buyPrice, stopLimitRangePips, groupLabel);
            PlaceStopLimitOrderAsync(TradeType.Sell, Symbol.Name, volume, sellPrice, stopLimitRangePips, groupLabel);
            
            Print($"[OCO PLACED] {groupLabel} | BuyStopLimit: {buyPrice:F4} | SellStopLimit: {sellPrice:F4} | Cap: {stopLimitRangePips}");
        }

        private void OnPendingOrderFilled(PendingOrderFilledEventArgs args)
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
                
                // Track API Open
                string candidateUid = pos.Label.Split('|')[0].Replace("Oco_", "");
                int horizon = ExtractHorizon(pos.Label);
                string reservationId = ExtractReservationId(pos.Label);
                TrackOpenTradeAsync(Symbol.Name, candidateUid, pos.Id.ToString(), pos.TradeType.ToString(), pos.EntryPrice, pos.EntryTime, horizon, reservationId);
            }
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            var pos = args.Position;
            if (pos.Label != null && pos.Label.StartsWith("Oco_"))
            {
                _posAgeBars.Remove(pos.Id);
                double pnlPips = pos.GrossProfit / (pos.VolumeInUnits * Symbol.PipValue); 
                double closePx = pos.TradeType == TradeType.Buy ? Symbol.Bid : Symbol.Ask;
                TrackUpdateTradeAsync(pos.Id.ToString(), "CLOSED", closePx, Server.Time, pnlPips);
            }
        }

        private string ExtractReservationId(string label)
        {
            int ridIdx = label.IndexOf("|RID", StringComparison.Ordinal);
            if (ridIdx == -1) return null;
            int nextSep = label.IndexOf("|", ridIdx + 1, StringComparison.Ordinal);
            if (nextSep == -1) nextSep = label.Length;
            string token = label.Substring(ridIdx + 4, nextSep - (ridIdx + 4));
            if (string.IsNullOrWhiteSpace(token) || token == "NA") return null;
            return token;
        }

        private async void TrackOpenTradeAsync(string symbol, string candidateUid, string brokerPosId, string side, double entryPrice, DateTime entryTs, int horizon, string reservationId = null)
        {
            try {
                var payload = new { symbol = symbol, candidate_uid = candidateUid, broker_pos_id = brokerPosId, side = side, entry_price = entryPrice, entry_ts = entryTs.ToUniversalTime().ToString("O"), horizon = horizon, reservation_id = reservationId };
                var content = new StringContent(JsonSerializer.Serialize(payload, _jsonOpts), Encoding.UTF8, "application/json");
                await _client.PostAsync($"{BaseUrl}/trades/open", content);
            } catch (Exception ex) { Print($"[API ERR] TrackOpenTradeAsync: {ex}"); }
        }

        private async void TrackUpdateTradeAsync(string brokerPosId, string status, double exitPrice, DateTime exitTs, double pnlPips)
        {
            try {
                var payload = new { symbol = _internalSymbol, broker_pos_id = brokerPosId, status = status, exit_price = exitPrice, exit_ts = exitTs.ToUniversalTime().ToString("O"), pnl_pips = pnlPips };
                var content = new StringContent(JsonSerializer.Serialize(payload, _jsonOpts), Encoding.UTF8, "application/json");
                await _client.PostAsync($"{BaseUrl}/trades/update", content);
            } catch (Exception ex) { Print($"[API ERR] TrackUpdateTradeAsync: {ex}"); }
        }

        private async void RecoverActiveTradesAsync()
        {
            try {
                var resp = await _client.GetAsync($"{BaseUrl}/trades/active?symbol={_internalSymbol}");
                if (resp.IsSuccessStatusCode)
                {
                    var body = await resp.Content.ReadAsStringAsync();
                    var activeTrades = JsonSerializer.Deserialize<List<ActiveTradeDTO>>(body, _jsonOpts);
                    if (activeTrades != null && activeTrades.Count > 0)
                    {
                        var statusResp = await _client.GetAsync($"{BaseUrl}/status");
                        if (statusResp.IsSuccessStatusCode)
                        {
                            var statusBody = await statusResp.Content.ReadAsStringAsync();
                            var statusList = JsonSerializer.Deserialize<List<StatusSymbolDTO>>(statusBody, _jsonOpts);
                            var myStatus = statusList?.FirstOrDefault(s => s.symbol == _internalSymbol);
                            if (myStatus != null)
                            {
                                int currentBarCount = myStatus.bar_count;
                                foreach (var t in activeTrades)
                                {
                                    if (int.TryParse(t.broker_pos_id, out int pid))
                                    {
                                        int elapsed = currentBarCount - t.entry_bar_id;
                                        _posAgeBars[pid] = Math.Max(0, elapsed);
                                        Print($"[RECOVERY] Hydrated POS {pid} - Age: {_posAgeBars[pid]} / {t.horizon}");
                                    }
                                }
                            }
                        }
                    }
                }
            } catch (Exception ex) { Print($"[API ERR] RecoverActiveTradesAsync: {ex}"); }
        }

        protected override void OnStop()
        {
            try
            {
                FlushTickQueue(skipPrediction: true);
            }
            catch (Exception ex)
            {
                Print($"[WARN] Flush on stop failed: {ex.Message}");
            }
            PendingOrders.Filled -= OnPendingOrderFilled;
            Positions.Closed -= OnPositionClosed;
            _client?.Dispose();
        }
    }

    public class TickPayload
    {
        public string symbol { get; set; }
        public string timestamp { get; set; }
        public double bid { get; set; }
        public double ask { get; set; }
        public double tick_volume { get; set; } = 1.0;
        public long client_tick_seq { get; set; }
    }

    public class TickResponse
    {
        public bool ok { get; set; }
        public string symbol { get; set; }
        public bool tick_accepted { get; set; } = true;
        public string drop_reason { get; set; }
        public int symbol_tick_seq { get; set; }
        public long? last_client_tick_seq { get; set; }
        public string last_tick_ts_utc { get; set; }
        public bool bar_completed { get; set; }
        public List<int> completed_bar_ticks { get; set; }
        public int bar_count { get; set; }
    }

    public class TickBatchResponse
    {
        public bool ok { get; set; }
        public string symbol { get; set; }
        public int ticks_received { get; set; }
        public int accepted_count { get; set; }
        public int dropped_count { get; set; }
        public bool bar_completed { get; set; }
        public List<int> completed_bar_ticks { get; set; }
        public int symbol_tick_seq { get; set; }
        public long? last_client_tick_seq { get; set; }
        public string last_tick_ts_utc { get; set; }
        public int bar_count { get; set; }
    }

    public class OcoPrediction
    {
        public string symbol { get; set; }
        public string candidate_uid { get; set; }
        public double pred_prob { get; set; }
        public double threshold_exec { get; set; }
        public int selected_exec { get; set; }
        public int bar_ticks { get; set; }
        public int horizon { get; set; }
        public double barrier_pips { get; set; }
        public double cap_pips { get; set; }
        public string threshold_source { get; set; }
        public string model_month { get; set; }
        public bool risk_blocked { get; set; }
        public string risk_block_reason { get; set; }
        public Dictionary<string, JsonElement> risk_metrics_snapshot { get; set; }
        public string risk_reservation_id { get; set; }
    }

    public class ActiveTradeDTO
    {
        public string broker_pos_id { get; set; }
        public int entry_bar_id { get; set; }
        public int horizon { get; set; }
        public int? touch_bar_id { get; set; }
    }

    public class StatusSymbolDTO
    {
        public string symbol { get; set; }
        public int bar_count { get; set; }
    }

    public class FtmoStatusDTO
    {
        public bool enabled { get; set; }
        public string symbol { get; set; }
        public string profile_id { get; set; }
        public bool allow_trading { get; set; }
        public string block_reason { get; set; }
        public bool snapshot_available { get; set; }
    }
}
