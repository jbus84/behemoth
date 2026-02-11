from __future__ import annotations

import argparse
import heapq
import itertools
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import redis


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pipelines.build_events_m15 import PAIRS as PAIRS_M15
from pipelines.build_events_m5 import PAIRS as PAIRS_M5
from services.api.risk import compute_target_notional
from services.api.settings import settings


PAIR_MAP = {
    "m5": PAIRS_M5,
    "m15": PAIRS_M15,
}


@dataclass
class ReplayEvent:
    bar: str
    strategy_id: str
    pair: str
    entry_ts: int
    exit_ts: int
    side: str
    active_leg: str
    pnl_bps: float
    duration_bars: int


def _now_ts() -> int:
    return int(time.time())


def _to_dt(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)


def _to_iso(ts_ns: int) -> str:
    return _to_dt(ts_ns).isoformat()


def _api_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


def _api_request(
    method: str, url: str, payload: dict | None = None, headers: dict | None = None
):
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode()
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            body = json.loads(raw) if raw else {}
            return resp.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"detail": raw.decode("utf-8", errors="ignore") if raw else ""}
        return exc.code, body


def _api_get_json(url: str) -> dict:
    status, body = _api_request("GET", url)
    if status >= 400:
        raise RuntimeError(f"GET {url} failed: {status} {body}")
    return body


def _fetch_events(base_url: str, bar: str, pair: str) -> list[dict]:
    path = f"/predictions/{bar}/{urllib.parse.quote(pair, safe='')}"
    payload = _api_get_json(_api_url(base_url, path))
    return payload.get("events", [])


def _get_progress_redis():
    url = os.getenv("REPLAY_REDIS_URL") or os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _update_progress(client, key: str, **fields: float | int | str | bool):
    if client is None:
        return
    payload = {"updated_at": _now_ts()}
    payload.update(fields)
    client.hset(key, mapping=payload)


def _build_events(base_url: str, bars: list[str], limit: int | None) -> list[ReplayEvent]:
    events: list[ReplayEvent] = []
    for bar in bars:
        if bar not in PAIR_MAP:
            raise SystemExit(f"Unknown bar: {bar}")
        strategy_id = f"mom_{bar}"
        pairs = [name for name, *_ in PAIR_MAP[bar]]
        for pair in pairs:
            rows = _fetch_events(base_url, bar, pair)
            for row in rows[:limit] if limit else rows:
                events.append(
                    ReplayEvent(
                        bar=bar,
                        strategy_id=strategy_id,
                        pair=pair,
                        entry_ts=int(row["entry_ts"]),
                        exit_ts=int(row["exit_ts"]),
                        side=str(row["side"]),
                        active_leg=str(row["active_leg"]),
                        pnl_bps=float(row["pnl_bps"]),
                        duration_bars=int(row["duration_bars"]),
                    )
                )
    events.sort(key=lambda e: e.entry_ts)
    return events


def main():
    parser = argparse.ArgumentParser(description="Replay bars via API for full simulation.")
    parser.add_argument("--bars", default="m5,m15", help="Comma-separated bars to replay.")
    parser.add_argument("--api-url", default=os.getenv("REPLAY_API_URL", "http://localhost:8001"))
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=None, help="Limit events per pair.")
    parser.add_argument("--progress-every", type=int, default=1000)
    args = parser.parse_args()

    bars = [b.strip() for b in args.bars.split(",") if b.strip()]
    base_url = args.api_url

    progress_client = _get_progress_redis()
    progress_every = max(int(args.progress_every), 1)

    events = _build_events(base_url, bars, args.limit)
    totals: dict[str, int] = {b: 0 for b in bars}
    for ev in events:
        totals[ev.bar] = totals.get(ev.bar, 0) + 1
    processed = {b: 0 for b in bars}
    opened = {b: 0 for b in bars}
    closed = {b: 0 for b in bars}
    skipped_guardrail = {b: 0 for b in bars}
    skipped_risk = {b: 0 for b in bars}
    risk_reasons = {b: {} for b in bars}
    start_time = {b: time.time() for b in bars}

    for bar in bars:
        _update_progress(progress_client, f"replay:progress:{bar}", total=totals.get(bar, 0))
        print(f"[{bar}] events={totals.get(bar, 0)}", flush=True)

    open_heap: list[tuple[int, int, str, float, float, str, str]] = []
    tie_breaker = itertools.count()
    equity_by_strategy: dict[str, float] = {}
    for strategy_id in {ev.strategy_id for ev in events}:
        try:
            state = _api_get_json(_api_url(base_url, f"/risk/{strategy_id}"))
            equity_by_strategy[strategy_id] = float(
                state.get("equity", settings.account_equity_start)
            )
        except Exception:
            equity_by_strategy[strategy_id] = settings.account_equity_start

    for ev in events:
        while open_heap and open_heap[0][0] <= ev.entry_ts:
            exit_ts, _, pos_id, pnl_bps, notional, strategy_id, bar = heapq.heappop(open_heap)
            close_payload = {"exit_ts": _to_iso(exit_ts), "pnl_bps": pnl_bps}
            _api_request("POST", _api_url(base_url, f"/positions/{pos_id}/close"), close_payload)
            closed[bar] += 1
            equity_by_strategy[strategy_id] = equity_by_strategy.get(
                strategy_id, settings.account_equity_start
            ) + notional * pnl_bps / 10000.0

        equity = equity_by_strategy.get(ev.strategy_id, settings.account_equity_start)
        notional = float(compute_target_notional(ev.strategy_id, ev.pair, equity))
        create_payload = {
            "strategy_id": ev.strategy_id,
            "pair": ev.pair,
            "side": ev.side,
            "active_leg": ev.active_leg,
            "size": float(notional),
            "entry_ts": _to_iso(ev.entry_ts),
            "metadata": {"bar": ev.bar, "duration_bars": ev.duration_bars},
        }
        status, body = _api_request(
            "POST",
            _api_url(base_url, "/positions"),
            create_payload,
            headers={"Idempotency-Key": f"{ev.strategy_id}:{ev.pair}:{ev.entry_ts}"},
        )
        if status >= 400:
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, dict):
                reason = str(detail.get("error", "unknown"))
                if reason == "guardrail_paused":
                    skipped_guardrail[ev.bar] += 1
                else:
                    skipped_risk[ev.bar] += 1
                    risk_reasons[ev.bar][reason] = risk_reasons[ev.bar].get(reason, 0) + 1
            else:
                skipped_risk[ev.bar] += 1
                risk_reasons[ev.bar]["unknown"] = risk_reasons[ev.bar].get("unknown", 0) + 1
            processed[ev.bar] += 1
            continue

        pos_id = body.get("id")
        if pos_id:
            _api_request(
                "POST",
                _api_url(base_url, f"/positions/{pos_id}/open"),
                {"entry_ts": _to_iso(ev.entry_ts)},
            )
            heapq.heappush(
                open_heap,
                (ev.exit_ts, next(tie_breaker), pos_id, ev.pnl_bps, notional, ev.strategy_id, ev.bar),
            )
            opened[ev.bar] += 1

        processed[ev.bar] += 1
        if processed[ev.bar] % progress_every == 0:
            elapsed = max(time.time() - start_time[ev.bar], 1e-6)
            rate = processed[ev.bar] / elapsed
            remaining = max(totals[ev.bar] - processed[ev.bar], 0)
            eta_s = remaining / rate if rate > 0 else 0.0
            progress_pct = (processed[ev.bar] / totals[ev.bar] * 100.0) if totals[ev.bar] else 0.0
            _update_progress(
                progress_client,
                f"replay:progress:{ev.bar}",
                processed=processed[ev.bar],
                opened=opened[ev.bar],
                closed=closed[ev.bar],
                skipped_guardrail=skipped_guardrail[ev.bar],
                skipped_risk=skipped_risk[ev.bar],
                rate=rate,
                eta_s=eta_s,
                progress_pct=progress_pct,
                total=totals[ev.bar],
                done=False,
            )
            print(
                f"[{ev.bar}] processed={processed[ev.bar]} opened={opened[ev.bar]} "
                f"closed={closed[ev.bar]} skipped_guardrail={skipped_guardrail[ev.bar]} "
                f"skipped_risk={skipped_risk[ev.bar]} rate={rate:.1f}/s",
                flush=True,
            )

        if args.sleep:
            time.sleep(args.sleep)

    while open_heap:
        exit_ts, _, pos_id, pnl_bps, notional, strategy_id, bar = heapq.heappop(open_heap)
        _api_request(
            "POST",
            _api_url(base_url, f"/positions/{pos_id}/close"),
            {"exit_ts": _to_iso(exit_ts), "pnl_bps": pnl_bps},
        )
        equity_by_strategy[strategy_id] = equity_by_strategy.get(
            strategy_id, settings.account_equity_start
        ) + notional * pnl_bps / 10000.0
        closed[bar] += 1

    for bar in bars:
        _update_progress(
            progress_client,
            f"replay:progress:{bar}",
            processed=processed[bar],
            opened=opened[bar],
            closed=closed[bar],
            skipped_guardrail=skipped_guardrail[bar],
            skipped_risk=skipped_risk[bar],
            rate=0.0,
            eta_s=0.0,
            progress_pct=100.0 if totals[bar] else 0.0,
            total=totals[bar],
            done=True,
        )
        if risk_reasons[bar]:
            print(f"[{bar}] risk_reasons={risk_reasons[bar]}", flush=True)


if __name__ == "__main__":
    main()
