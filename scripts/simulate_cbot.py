#!/usr/bin/env python3
"""
Simulate the cBot polling loop entirely in Python.

Usage:
    python scripts/simulate_cbot.py --api-url http://localhost:8000 --interval 5 --bar m15

This mimics exactly what the C# cBot does:
1. Poll GET /signals/{bar}
2. For each signal, create + open a position via the API
3. Track open positions and close them after a timeout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TrackedPosition:
    position_id: str
    pair: str
    side: str
    opened_at: float  # time.time()
    entry_price: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api(method: str, url: str, payload: dict | None = None, headers: dict | None = None):
    """Make an HTTP request and return (status, body)."""
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode()
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"detail": raw.decode("utf-8", errors="ignore") if raw else ""}
        return exc.code, body
    except Exception as exc:
        return 599, {"detail": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Simulate cBot polling loop.")
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--bar", default="m15", help="Bar size (m5 or m15)")
    parser.add_argument("--interval", type=float, default=10.0, help="Polling interval (seconds)")
    parser.add_argument("--timeout-mins", type=int, default=120, help="Position timeout (minutes)")
    parser.add_argument("--lot-size", type=float, default=0.05, help="Lot size for notional calc")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max polling cycles (0=infinite)")
    args = parser.parse_args()

    base = args.api_url.rstrip("/")
    bar = args.bar
    timeout_s = args.timeout_mins * 60
    open_positions: dict[str, TrackedPosition] = {}

    print(f"=== Behemoth cBot Simulator ===")
    print(f"  API:      {base}")
    print(f"  Bar:      {bar}")
    print(f"  Interval: {args.interval}s")
    print(f"  Timeout:  {args.timeout_mins}m")
    print()

    # Verify API is reachable
    status, body = _api("GET", f"{base}/healthz")
    if status >= 400:
        print(f"ERROR: API not reachable at {base} — {body}")
        sys.exit(1)
    print(f"API healthy: {body}\n")

    cycle = 0
    while True:
        cycle += 1
        now = time.time()
        now_iso = _now_iso()

        # ── Close timed-out positions ──
        to_close = [pid for pid, tp in open_positions.items() if now - tp.opened_at > timeout_s]
        for pid in to_close:
            tp = open_positions.pop(pid)
            close_payload = {
                "exit_price": 0.0,
                "exit_ts": now_iso,
                "pnl_bps": 0.0,  # Unknown without market data
            }
            status, body = _api("POST", f"{base}/positions/{tp.position_id}/close", close_payload)
            print(f"  TIMEOUT_CLOSE: {tp.pair} {tp.side} → {status}")

        # ── Fetch signals ──
        url = f"{base}/signals/{bar}?current_time={urllib.parse.quote(now_iso)}"
        status, body = _api("GET", url)

        if status >= 400:
            print(f"[Cycle {cycle}] Signal fetch failed: {status} {body}")
            time.sleep(args.interval)
            continue

        signals = body.get("signals", [])
        checked = body.get("checked_pairs", 0)
        print(f"[Cycle {cycle}] Checked {checked} pairs → {len(signals)} signal(s)")

        # ── Process each signal ──
        for sig in signals:
            pair = sig["pair"]
            side = sig["side"]
            label = f"{pair}_{side}"

            # Skip if already have this position open
            if label in open_positions:
                print(f"  SKIP: {label} already open")
                continue

            # Create position
            create_payload = {
                "strategy_id": f"mom_{bar}",
                "pair": pair,
                "side": side,
                "active_leg": sig["active_leg"],
                "size": args.lot_size * 100000,
                "entry_ts": now_iso,
                "metadata": {"bar": bar, "z_score": sig["z_score"], "beta": sig["beta"]},
            }
            idem_key = f"sim:{bar}:{pair}:{now_iso[:16]}"
            status, body = _api(
                "POST", f"{base}/positions", create_payload,
                headers={"Idempotency-Key": idem_key},
            )

            if status >= 400:
                detail = body.get("detail", body)
                print(f"  REJECTED: {pair} {side} → {detail}")
                continue

            pos_id = body.get("id")
            if not pos_id:
                print(f"  ERROR: No position ID returned for {pair}")
                continue

            # Open position
            open_payload = {"entry_price": 0.0, "entry_ts": now_iso}
            _api("POST", f"{base}/positions/{pos_id}/open", open_payload)

            open_positions[label] = TrackedPosition(
                position_id=pos_id, pair=pair, side=side, opened_at=now,
            )
            z = sig["z_score"]
            active = sig["active_leg"]
            symbol = sig["leg_y"] if active == "Y" else sig["leg_x"]
            print(f"  OPENED: {pair} {side} (z={z:.2f}, leg={active}→{symbol}, id={pos_id[:8]})")

        print(f"  Open positions: {len(open_positions)}")

        if 0 < args.max_cycles <= cycle:
            print(f"\nMax cycles ({args.max_cycles}) reached. Stopping.")
            break

        time.sleep(args.interval)

    # Close all remaining
    print(f"\nClosing {len(open_positions)} remaining position(s)...")
    for pid, tp in open_positions.items():
        _api("POST", f"{base}/positions/{tp.position_id}/close", {
            "exit_price": 0.0, "exit_ts": _now_iso(), "pnl_bps": 0.0,
        })
        print(f"  CLOSED: {tp.pair} {tp.side}")

    print("Done.")


if __name__ == "__main__":
    main()
