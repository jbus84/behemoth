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

# ---------------------------------------------------------------------------
# Legacy prompts (kept for backward compatibility)
# ---------------------------------------------------------------------------


def build_prompt(parent_src: str, parent_score: float, logs: str, idea: str, rules: str = _RULES) -> str:
    return (
        "Improve this dispersion residual program to increase its score.\n\n"
        f"{rules}\n"
        f"Research idea to consider: {idea}\n\n"
        f"Parent score: {parent_score}\n"
        f"Parent logs: {logs[:500]}\n\n"
        f"Parent program:\n```python\n{parent_src}\n```\n"
    )


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


# ---------------------------------------------------------------------------
# Branch-aware rich prompts (new)
# ---------------------------------------------------------------------------

def build_branch_prompt(parent_src: str, parent_score: float, logs: str,
                        branch: str, rich_template: str,
                        rules: str = _RULES) -> str:
    """Rich prompt using the full branch template (formula + rationale + reference)."""
    return (
        f"{rich_template}\n\n"
        f"PARENT PROGRAM (your starting point):\n```python\n{parent_src}\n```\n\n"
        f"Parent score: {parent_score:.3f}\n"
        f"Parent logs: {logs[:500]}\n\n"
        "YOUR TASK:\n"
        "Write a NEW signal(ctx) that improves on the parent. You may vary parameters within the allowed "
        "ranges, or combine with another gate/direction idea if you see a sensible crossover. "
        "Output ONLY one ```python block.\n"
    )


def build_cross_branch_prompt(srcA: str, scoreA: float, branchA: str,
                              srcB: str, scoreB: float, branchB: str,
                              cross_text: str, rules: str = _RULES) -> str:
    """Semantic recombination prompt when parents are from different branches."""
    return (
        f"{cross_text}\n\n"
        f"PARENT A ({branchA}, score {scoreA:.3f}):\n"
        f"```python\n{srcA}\n```\n\n"
        f"PARENT B ({branchB}, score {scoreB:.3f}):\n"
        f"```python\n{srcB}\n```\n\n"
        "YOUR TASK:\n"
        "Write a single NEW signal(ctx) that combines the best ideas from BOTH parents. "
        "Output ONLY one ```python block.\n"
    )


# ---------------------------------------------------------------------------
# Callers / extractors (unchanged)
# ---------------------------------------------------------------------------


def extract_program(resp: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", resp, re.DOTALL)
    src = (m.group(1) if m else resp).strip()
    return src


def _ollama_caller(prompt: str) -> str:
    """Call the cheap LLM. A timeout or non-zero exit yields "" (a failed expansion the
    search rejects) rather than crashing the whole run on a single slow network call."""
    try:
        out = subprocess.run(
            [str(ROOT / "scripts/cheap_llm.sh"), prompt],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return ""
    return out.stdout if out.returncode == 0 else ""


# ---------------------------------------------------------------------------
# Legacy wrappers (kept for backward compatibility)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Branch-aware wrappers (new)
# ---------------------------------------------------------------------------

def propose_branch_program(parent_src, parent_score, logs, branch: str,
                           rich_template: str, cache_dir, caller=None):
    """Expand a node staying within its literature branch (rich template)."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_branch_prompt(parent_src, parent_score, logs, branch, rich_template)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"branch_{branch}_{key}.py"
    if cached.exists():
        return cached.read_text()
    src = extract_program(caller(prompt))
    if src.strip():
        cached.write_text(src)
    return src


def recombine_branch_program(srcA, scoreA, branchA: str,
                             srcB, scoreB, branchB: str,
                             cross_text: str, cache_dir, caller=None):
    """Recombine two nodes, with semantic cross-branch context if branches differ."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_cross_branch_prompt(srcA, scoreA, branchA, srcB, scoreB, branchB, cross_text)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    # Include both branches in cache key so A+B and B+A share a cache entry
    branches = sorted([branchA, branchB])
    cached = cache_dir / f"cross_{branches[0]}_{branches[1]}_{key}.py"
    if cached.exists():
        return cached.read_text()
    src = extract_program(caller(prompt))
    if src.strip():
        cached.write_text(src)
    return src
