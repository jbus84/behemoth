from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.settings import settings
from services.api.validation import PIPELINE_PATHS, compute_summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_baseline(bar: str, bar_minutes: int, path: Path) -> dict:
    summary = compute_summary(str(path), bar_minutes, guardrail=False)
    guardrail_summary = compute_summary(str(path), bar_minutes, guardrail=True)

    payload = {
        "bar": bar,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_path": str(path),
        "pipeline_sha256": _sha256(path),
        "guardrail_settings": {
            "loss_threshold": settings.guardrail_loss_threshold,
            "loss_streak": settings.guardrail_loss_streak,
            "cooldown_days": settings.guardrail_cooldown_days,
        },
        "summary": summary,
        "summary_guardrail": guardrail_summary,
    }

    out_dir = Path("data/baselines")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"baseline_{bar}.json"
    out_json.write_text(json.dumps(payload, indent=2))

    out_csv = out_dir / f"baseline_{bar}.csv"
    out_csv.write_text(
        "variant,trades,win_rate,mean_pnl,total_pnl,max_dd,sharpe,sharpe_active,sharpe_trade\n"
        + f"baseline,{summary['trades']},{summary['win_rate']},{summary['mean_pnl']},{summary['total_pnl']},{summary['max_dd']},{summary['sharpe']},{summary['sharpe_active']},{summary['sharpe_trade']}\n"
        + f"guardrail,{guardrail_summary['trades']},{guardrail_summary['win_rate']},{guardrail_summary['mean_pnl']},{guardrail_summary['total_pnl']},{guardrail_summary['max_dd']},{guardrail_summary['sharpe']},{guardrail_summary['sharpe_active']},{guardrail_summary['sharpe_trade']}\n"
    )

    return payload


def main() -> None:
    if "m5" not in PIPELINE_PATHS or "m15" not in PIPELINE_PATHS:
        raise SystemExit("Missing pipeline paths for m5/m15")

    m5_path = Path(PIPELINE_PATHS["m5"])
    m15_path = Path(PIPELINE_PATHS["m15"])
    if not m5_path.exists():
        raise SystemExit(f"M5 pipeline file missing: {m5_path}")
    if not m15_path.exists():
        raise SystemExit(f"M15 pipeline file missing: {m15_path}")

    _write_baseline("m5", 5, m5_path)
    _write_baseline("m15", 15, m15_path)
    print("Baselines written to data/baselines/")


if __name__ == "__main__":
    main()
