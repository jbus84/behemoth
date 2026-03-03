"""Lightweight monitoring dashboard for the Behemoth OCO strategy.

Served as a FastAPI sub-application mounted on the main server.
Provides a single-page HTML dashboard showing:
    - Per-symbol model status (loaded month, threshold)
    - DuckDB buffer depth per symbol
    - Last prediction results
    - System health
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Behemoth OCO Dashboard</title>
    <style>
        :root {
            --bg: #0f1117;
            --surface: #1a1d2e;
            --border: #2a2d3e;
            --text: #e4e4e7;
            --muted: #71717a;
            --accent: #6366f1;
            --green: #22c55e;
            --amber: #f59e0b;
            --red: #ef4444;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1d2e 0%, #0f1117 100%);
            border-bottom: 1px solid var(--border);
            padding: 1.5rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 {
            font-size: 1.25rem;
            font-weight: 600;
            background: linear-gradient(135deg, #818cf8, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }
        .status-ok { background: rgba(34,197,94,0.15); color: var(--green); }
        .status-warn { background: rgba(245,158,11,0.15); color: var(--amber); }
        .status-err { background: rgba(239,68,68,0.15); color: var(--red); }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 1rem;
            padding: 1.5rem 2rem;
        }
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            padding: 1.25rem;
            transition: border-color 0.2s;
        }
        .card:hover { border-color: var(--accent); }
        .card-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.75rem;
        }
        .symbol-name {
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 0.35rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.8125rem;
        }
        .metric-row:last-child { border-bottom: none; }
        .metric-label { color: var(--muted); }
        .metric-value { font-weight: 500; font-variant-numeric: tabular-nums; }
        .refresh-bar {
            padding: 0.75rem 2rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.75rem;
            color: var(--muted);
        }
        .refresh-bar button {
            background: var(--accent);
            color: white;
            border: none;
            padding: 0.35rem 0.75rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 500;
        }
        .refresh-bar button:hover { opacity: 0.9; }
        #last-update { font-variant-numeric: tabular-nums; }
    </style>
</head>
<body>
    <div class="header">
        <h1>BEHEMOTH &mdash; OCO Strategy Monitor</h1>
        <span id="sys-status" class="status-badge status-warn">loading&hellip;</span>
    </div>
    <div class="refresh-bar">
        <button onclick="refresh()">Refresh</button>
        <span>Last update: <span id="last-update">—</span></span>
        <span style="margin-left:auto">Auto-refresh: 30s</span>
    </div>
    <div class="grid" id="cards"></div>

    <script>
        async function refresh() {
            try {
                const [health, status] = await Promise.all([
                    fetch('/health').then(r => r.json()),
                    fetch('/status').then(r => r.json()),
                ]);

                // System badge
                const badge = document.getElementById('sys-status');
                if (health.status === 'ok') {
                    badge.textContent = 'OPERATIONAL';
                    badge.className = 'status-badge status-ok';
                } else {
                    badge.textContent = 'NO MODELS';
                    badge.className = 'status-badge status-warn';
                }

                // Cards
                const grid = document.getElementById('cards');
                grid.innerHTML = '';
                for (const s of status) {
                    const card = document.createElement('div');
                    card.className = 'card';
                    const modelStatus = s.model_loaded
                        ? `<span style="color:var(--green)">✓ ${s.model_month}</span>`
                        : `<span style="color:var(--red)">✗ not loaded</span>`;
                    const warmup = health.bar_counts[s.symbol] || 0;
                    const warmupColor = warmup >= 289 ? 'var(--green)' : warmup > 0 ? 'var(--amber)' : 'var(--red)';
                    card.innerHTML = `
                        <div class="card-title">Symbol</div>
                        <div class="symbol-name">${s.symbol}</div>
                        <div class="metric-row">
                            <span class="metric-label">Model</span>
                            <span class="metric-value">${modelStatus}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Threshold</span>
                            <span class="metric-value">${s.has_threshold ? '✓' : '—'}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">Buffer depth</span>
                            <span class="metric-value" style="color:${warmupColor}">${warmup} bars</span>
                        </div>
                    `;
                    grid.appendChild(card);
                }

                document.getElementById('last-update').textContent =
                    new Date().toLocaleTimeString();
            } catch (e) {
                const badge = document.getElementById('sys-status');
                badge.textContent = 'OFFLINE';
                badge.className = 'status-badge status-err';
            }
        }

        refresh();
        setInterval(refresh, 30000);
    </script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the single-page monitoring dashboard."""
    return HTMLResponse(content=_DASHBOARD_HTML)
