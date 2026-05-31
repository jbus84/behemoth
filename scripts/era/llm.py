from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_RULES = (
    "You write a Python function `residual(ctx) -> np.ndarray`.\n"
    "ctx gives ONLY causal cross-section data: ctx.r (n_bars x 6 USD-aligned\n"
    "vol-normalised returns), ctx.target_col(), ctx.peers(), ctx.target_idx,\n"
    "ctx.names, ctx.usd_sign. ctx.hour gives the per-bar UTC hour (int array).\n"
    "ctx.dispersion() gives the per-bar cross-sectional std. `np` is available.\n"
    "You CANNOT import anything and CANNOT access future returns / y_fwd / labels\n"
    "(they are not in ctx). Return a per-bar residual; larger |residual| ==\n"
    "stronger idiosyncratic dislocation of the target. You MAY gate: return np.nan\n"
    "for bars you DO NOT want to trade (the scorer ignores non-finite entries).\n"
    "E.g. trade only the asia session (UTC hour 0-5) or only high-dispersion bars.\n"
    "ctx.r is the FULL split: shape (n_bars x 6), rows ordered in time. You MAY\n"
    "use the time axis for stateful dispersion ideas (causal/bounded only):\n"
    "trailing-window or expanding stats, EWMA/rolling residuals, dispersion-change\n"
    "over a lookback, rolling correlation/PCA peer structure. HARD RULE: never read\n"
    "future rows - residual[k] must depend ONLY on bars <= k (use r[k-W:k], not\n"
    "r[k:], no centered windows, no full-split mean/median/std). A causality probe\n"
    "perturbs future rows and REJECTS any program whose past output changes.\n"
    "Output ONLY one ```python code block.\n"
)


def build_prompt(parent_src: str, parent_score: float, logs: str, idea: str, rules: str = _RULES) -> str:
    return (
        "Improve this dispersion residual program to increase its score.\n\n"
        f"{rules}\n"
        f"Research idea to consider: {idea}\n\n"
        f"Parent score: {parent_score}\n"
        f"Parent logs: {logs[:500]}\n\n"
        f"Parent program:\n```python\n{parent_src}\n```\n"
    )


def extract_program(resp: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", resp, re.DOTALL)
    src = (m.group(1) if m else resp).strip()
    return src


def _ollama_caller(prompt: str) -> str:
    """A timeout or non-zero exit yields "" (a failed expansion the search rejects)
    rather than crashing the whole run on a single slow network call."""
    try:
        out = subprocess.run(
            [str(ROOT / "scripts/cheap_llm.sh"), prompt],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return ""
    return out.stdout if out.returncode == 0 else ""


def propose_program(parent_src, parent_score, logs, idea, cache_dir, caller=None, rules=_RULES):
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(parent_src, parent_score, logs, idea, rules=rules)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"{key}.py"
    if cached.exists():
        return cached.read_text()
    src = extract_program(caller(prompt))
    if src.strip():  # don't cache empty (transient LLM failure) — allow retry next run
        cached.write_text(src)
    return src


def build_recombine_prompt(srcA: str, scoreA: float, srcB: str, scoreB: float, rules: str = _RULES) -> str:
    return (
        "Combine these two dispersion residual programs by studying both and writing ONE new program.\n\n"
        f"{rules}\n"
        f"Parent A score: {scoreA}\n"
        f"Parent A program:\n```python\n{srcA}\n```\n\n"
        f"Parent B score: {scoreB}\n"
        f"Parent B program:\n```python\n{srcB}\n```\n\n"
        "Write a single new `residual(ctx)` that combines the best ideas from both.\n"
    )


def recombine_program(srcA, scoreA, srcB, scoreB, cache_dir, caller=None, rules=_RULES):
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_recombine_prompt(srcA, scoreA, srcB, scoreB, rules=rules)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"{key}.py"
    if cached.exists():
        return cached.read_text()
    src = extract_program(caller(prompt))
    if src.strip():
        cached.write_text(src)
    return src
