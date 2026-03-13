using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using cAlgo.API;
using cAlgo.API.Internals;

namespace cAlgo.Plugins
{
    /// <summary>
    /// Minimal custom-data source plugin scaffold for cTrader Backtesting.
    /// Reads a HistData export package created by scripts/export_ctrader_custom_data.py.
    /// </summary>
    [Plugin(AccessRights = AccessRights.FullAccess)]
    public class CustomDataSourceHistDataPlugin : Plugin
    {
        private const string ActivePackagePointerPath =
            "/Users/danielfisher/repositories/behemoth/data/analysis/backtest_reconcile/ctrader_active_custom_data_package.txt";

        // Update this path in cTrader or extend this plugin with a UI picker.
        private const string DefaultPackagePath =
            "/Users/danielfisher/repositories/behemoth/data/analysis/backtest_reconcile/EURUSD_histdata_custom_20250707_20250709";

        private BacktestingDataSource _dataSource;
        private ManifestModel _manifest;
        private List<TickRow> _ticks = new List<TickRow>();

        protected override void OnStart()
        {
            try
            {
                string packagePath = ResolvePackagePath();
                LoadPackage(packagePath);

                var options = new BacktestingDataSourceOptions(
                    BacktestingDataSourceDataType.Tick,
                    OnMinMaxTimeRequested,
                    OnDataRequested
                );
                _dataSource = Backtesting.DataSources.Add("HistDataCSV", options);
                Print($"HistDataCSV custom source registered. package={packagePath} rows={_ticks.Count}");
            }
            catch (Exception ex)
            {
                Print($"HistDataCSV plugin failed to start: {ex.Message}");
            }
        }

        protected override void OnStop()
        {
            _dataSource = null;
        }

        private BacktestingMinMaxTime OnMinMaxTimeRequested(BacktestingDataSourceMinMaxTimeArgs args)
        {
            if (_manifest == null)
            {
                throw new InvalidOperationException("Manifest not loaded.");
            }
            return new BacktestingMinMaxTime(_manifest.StartTsUtc, _manifest.EndTsUtc);
        }

        private void OnDataRequested(BacktestingDataRequest request)
        {
            if (_manifest == null || _ticks.Count == 0)
            {
                request.Fail("No custom tick data loaded.");
                return;
            }

            if (request.DataType != BacktestingDataSourceDataType.Tick)
            {
                request.Fail("Only tick data is supported by this scaffold.");
                return;
            }

            var slice = _ticks.Where(t => t.TimestampUtc >= request.StartTime && t.TimestampUtc < request.EndTime);
            var ticks = slice.Select(t => new BacktestingTick(t.TimestampUtc, t.Bid, t.Ask)).ToList();
            request.Complete(new BacktestingTickData(ticks));
        }

        private static string ResolvePackagePath()
        {
            try
            {
                if (File.Exists(ActivePackagePointerPath))
                {
                    string raw = File.ReadAllText(ActivePackagePointerPath).Trim();
                    if (!string.IsNullOrWhiteSpace(raw))
                    {
                        return raw;
                    }
                }
            }
            catch
            {
                // Fall back to the default package path if the pointer file is unreadable.
            }
            return DefaultPackagePath;
        }

        private void LoadPackage(string packagePath)
        {
            if (string.IsNullOrWhiteSpace(packagePath))
            {
                throw new InvalidOperationException("Package path is empty.");
            }

            string root = Path.GetFullPath(packagePath);
            string manifestPath = Path.Combine(root, "manifest.json");
            if (!File.Exists(manifestPath))
            {
                throw new FileNotFoundException("manifest.json not found", manifestPath);
            }

            string json = File.ReadAllText(manifestPath);
            using var doc = JsonDocument.Parse(json);
            var rootEl = doc.RootElement;

            string symbol = rootEl.GetProperty("symbol").GetString() ?? string.Empty;
            DateTime startTs = DateTime.Parse(
                rootEl.GetProperty("start_ts").GetString() ?? string.Empty,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal
            );
            DateTime endTs = DateTime.Parse(
                rootEl.GetProperty("end_ts").GetString() ?? string.Empty,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal
            );

            var files = new List<string>();
            foreach (var fileEl in rootEl.GetProperty("files").EnumerateArray())
            {
                string rel = fileEl.GetProperty("path").GetString() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(rel))
                {
                    files.Add(rel);
                }
            }

            var rows = new List<TickRow>();
            foreach (string relPath in files)
            {
                string fullPath = Path.GetFullPath(Path.Combine(root, relPath));
                if (!File.Exists(fullPath))
                {
                    throw new FileNotFoundException("tick csv not found", fullPath);
                }
                rows.AddRange(ReadTickCsv(fullPath));
            }

            _manifest = new ManifestModel
            {
                Symbol = symbol,
                StartTsUtc = DateTime.SpecifyKind(startTs, DateTimeKind.Utc),
                EndTsUtc = DateTime.SpecifyKind(endTs, DateTimeKind.Utc),
                Files = files,
            };
            _ticks = rows.OrderBy(r => r.TimestampUtc).ToList();
        }

        private static IEnumerable<TickRow> ReadTickCsv(string path)
        {
            bool header = true;
            foreach (string line in File.ReadLines(path))
            {
                if (header)
                {
                    header = false;
                    continue;
                }
                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                var parts = line.Split(',');
                if (parts.Length < 3)
                {
                    continue;
                }

                DateTime ts = DateTime.Parse(
                    parts[0],
                    CultureInfo.InvariantCulture,
                    DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal
                );
                double bid = double.Parse(parts[1], CultureInfo.InvariantCulture);
                double ask = double.Parse(parts[2], CultureInfo.InvariantCulture);
                yield return new TickRow
                {
                    TimestampUtc = DateTime.SpecifyKind(ts, DateTimeKind.Utc),
                    Bid = bid,
                    Ask = ask,
                };
            }
        }

        private class ManifestModel
        {
            public string Symbol { get; set; }
            public DateTime StartTsUtc { get; set; }
            public DateTime EndTsUtc { get; set; }
            public List<string> Files { get; set; }
        }

        private class TickRow
        {
            public DateTime TimestampUtc { get; set; }
            public double Bid { get; set; }
            public double Ask { get; set; }
        }
    }
}
