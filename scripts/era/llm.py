from __future__ import annotations

import hashlib
import json
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
# Extractors
# ---------------------------------------------------------------------------


def extract_program(resp: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", resp, re.DOTALL)
    src = (m.group(1) if m else resp).strip()
    return src


def extract_prior_prob(resp: str) -> float:
    """Parse LLM self-assessed confidence from response text.

    Looks for patterns like 'confidence: 0.85' or 'prior_prob: 0.7'.
    Returns 0.5 (neutral) if not found.
    """
    m = re.search(r"(?:confidence|prior_prob|prior|confidence score)[:=\s]+(\d\.?\d*)", resp, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.5


def extract_program_with_prior(resp: str) -> tuple[str, float]:
    """Extract both program source and LLM confidence score."""
    src = extract_program(resp)
    prior = extract_prior_prob(resp)
    return src, prior


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
# Dimension-locked atomic prompts (new — zarrduck-inspired)
# ---------------------------------------------------------------------------

def build_dimension_locked_prompt(parent_src: str, parent_score: float, logs: str,
                                    branch: str, rich_template: str,
                                    target_dimension: str, rules: str = _RULES) -> str:
    """Force the LLM to make exactly ONE atomic tweak in a specific dimension.

    target_dimension is a concept name from CONCEPT_TAXONOMY, e.g. 'roll_bounce',
    'barzykin_impact', 'taylor_adaptive_alpha'.  The prompt tells the LLM to
    vary ONLY that dimension while keeping everything else identical.
    """
    return (
        f"{rich_template}\n\n"
        f"PARENT PROGRAM (your starting point):\n```python\n{parent_src}\n```\n\n"
        f"Parent score: {parent_score:.3f}\n"
        f"Parent logs: {logs[:500]}\n\n"
        f"YOUR TASK:\n"
        f"Make EXACTLY ONE atomic tweak focused on the '{target_dimension}' dimension.\n"
        f"You may vary parameters, add/remove a gate, or adjust a weight, but ONLY\n"
        f"within the '{target_dimension}' concept.  Keep ALL other parts of the program\n"
        f"IDENTICAL to the parent.  Output ONLY one ```python block.\n"
        f"Also include your confidence (0-1) that this tweak will improve the score,\n"
        f"e.g. 'confidence: 0.85'.\n"
    )


def build_self_correct_prompt(parent_src: str, error_log: str,
                              branch: str, rich_template: str,
                              rules: str = _RULES) -> str:
    """When sandbox/static_check rejects a candidate, ask LLM to fix it.

    Sends the parent baseline + error log so the LLM can repair the candidate
    while preserving the original function signatures.
    """
    return (
        f"{rich_template}\n\n"
        f"The following program failed validation.  Please FIX the error while keeping\n"
        f"the core logic intact.  Do NOT change the function signature.\n\n"
        f"ERROR LOG:\n```\n{error_log[:800]}\n```\n\n"
        f"FAILED PROGRAM:\n```python\n{parent_src}\n```\n\n"
        f"Output ONLY the corrected ```python block.\n"
    )


# ---------------------------------------------------------------------------
# Atomic composition helpers (new — for --atomic-mode)
# ---------------------------------------------------------------------------

def _composition_to_json(comp: dict) -> str:
    return json.dumps(comp, indent=2, default=str)


def build_atomic_propose_prompt(parent_comp: dict, parent_score: float,
                                 target_slot: str, new_concept: str) -> str:
    """Prompt LLM to change ONE operator slot in a composition."""
    return (
        "You are evolving a fair-price estimator by modifying atomic microstructure operators.\n"
        "The current composition is a JSON object with skeleton, operators, and parameters.\n\n"
        f"CURRENT COMPOSITION (score {parent_score:.3f}):\n"
        f"```json\n{_composition_to_json(parent_comp)}\n```\n\n"
        f"YOUR TASK:\n"
        f"Change ONLY the '{target_slot}' operator to '{new_concept}'.\n"
        f"Keep all other operators and the skeleton identical.\n"
        f"Fill in sensible parameter values for the new operator (use the allowed ranges shown in comments).\n"
        f"Output ONLY a JSON object with the updated composition — no prose, no markdown, no python.\n"
        f"Format: {{\"skeleton\": \"...\", \"operators\": {{...}}, \"params\": {{...}}}}\n"
    )


def build_atomic_recombine_prompt(compA: dict, scoreA: float,
                                    compB: dict, scoreB: float) -> str:
    """Prompt LLM to merge two atomic compositions."""
    return (
        "You are combining two fair-price estimators into one better composition.\n\n"
        f"PARENT A (score {scoreA:.3f}):\n"
        f"```json\n{_composition_to_json(compA)}\n```\n\n"
        f"PARENT B (score {scoreB:.3f}):\n"
        f"```json\n{_composition_to_json(compB)}\n```\n\n"
        f"YOUR TASK:\n"
        f"Merge the best ideas from BOTH parents into a single composition.\n"
        f"You may take the base from one parent and the correction from the other,\n"
        f"or keep both corrections and blend them, or choose a new skeleton if needed.\n"
        f"Output ONLY a JSON object — no prose, no markdown, no python.\n"
        f"Format: {{\"skeleton\": \"...\", \"operators\": {{...}}, \"params\": {{...}}}}\n"
    )


def extract_composition(resp: str) -> dict:
    """Parse a JSON composition from LLM response. Returns {} on failure.

    Uses a brace-balancing scan so nested JSON objects are parsed correctly
    even when the response contains multiple JSON blocks or prose.
    """
    # Try each '{' position with a simple brace counter
    for start in range(len(resp)):
        if resp[start] != "{":
            continue
        depth = 0
        for end in range(start, len(resp)):
            if resp[end] == "{":
                depth += 1
            elif resp[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(resp[start:end + 1])
                    except json.JSONDecodeError:
                        break  # malformed at this start; try next
    return {}


def extract_composition_with_prior(resp: str) -> tuple[dict, float]:
    """Parse both composition and confidence from LLM response."""
    comp = extract_composition(resp)
    prior = extract_prior_prob(resp)
    return comp, prior


def build_atomic_extract_prompt(source: str, original_comp: dict) -> str:
    return (
        "You are analyzing a Python function that estimates a fair price.\n"
        "This function was originally generated from the following atomic composition:\n"
        f"```json\n{_composition_to_json(original_comp)}\n```\n\n"
        "Here is the corrected source code:\n"
        f"```python\n{source}\n```\n\n"
        "Your task: reverse-engineer the corrected source back into the atomic composition format.\n"
        "Identify which operators from the original composition are still present (possibly with modified parameters), "
        "and which new operators have been introduced. Output ONLY a JSON object in this exact format:\n"
        '{"skeleton": "...", "operators": {"slot_name": "operator_name", ...}, "params": {"param_name": value, ...}}\n'
    )


def extract_composition_from_source(source: str, original_comp: dict, cache_dir, caller=None) -> dict | None:
    """Attempt to recover an atomic composition dict from a corrected source string."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_atomic_extract_prompt(source, original_comp)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"atomic_extract_{key}.json"
    if cached.exists():
        try:
            return json.loads(cached.read_text())
        except json.JSONDecodeError:
            pass
    resp = caller(prompt)
    comp = extract_composition(resp)
    if comp:
        cached.write_text(json.dumps(comp))
    return comp if comp else None


def propose_atomic_change(parent_comp, parent_score, target_slot: str,
                          new_concept: str, cache_dir, caller=None) -> tuple[dict, float]:
    """Ask LLM to change one operator slot in a composition."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_atomic_propose_prompt(parent_comp, parent_score, target_slot, new_concept)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"atomic_propose_{target_slot}_{new_concept}_{key}.json"
    if cached.exists():
        text = cached.read_text()
        parts = text.split("\n---PRIOR---\n")
        if len(parts) == 2:
            try:
                return json.loads(parts[0]), float(parts[1])
            except (json.JSONDecodeError, ValueError):
                pass
        try:
            return json.loads(text), 0.5
        except json.JSONDecodeError:
            pass
    resp = caller(prompt)
    comp, prior = extract_composition_with_prior(resp)
    if comp:
        cached.write_text(json.dumps(comp) + "\n---PRIOR---\n" + str(prior))
    return comp, prior


def recombine_atomic_compositions(compA, scoreA, compB, scoreB, cache_dir, caller=None) -> tuple[dict, float]:
    """Ask LLM to merge two atomic compositions."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_atomic_recombine_prompt(compA, scoreA, compB, scoreB)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"atomic_recombine_{key}.json"
    if cached.exists():
        text = cached.read_text()
        parts = text.split("\n---PRIOR---\n")
        if len(parts) == 2:
            try:
                return json.loads(parts[0]), float(parts[1])
            except (json.JSONDecodeError, ValueError):
                pass
        try:
            return json.loads(text), 0.5
        except json.JSONDecodeError:
            pass
    resp = caller(prompt)
    comp, prior = extract_composition_with_prior(resp)
    if comp:
        cached.write_text(json.dumps(comp) + "\n---PRIOR---\n" + str(prior))
    return comp, prior


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


def propose_branch_program_with_prior(parent_src, parent_score, logs, branch: str,
                                      rich_template: str, cache_dir, caller=None) -> tuple[str, float]:
    """Expand a node and also extract LLM self-assessed confidence (prior_prob)."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_branch_prompt(parent_src, parent_score, logs, branch, rich_template)
    # Augment prompt to request confidence
    prompt += "\n\nAlso include your confidence (0-1) that this program will improve the score, e.g. 'confidence: 0.85'.\n"
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"branch_prior_{branch}_{key}.py"
    if cached.exists():
        text = cached.read_text()
        parts = text.split("\n---PRIOR---\n")
        if len(parts) == 2:
            return parts[0], float(parts[1])
        return text, 0.5
    resp = caller(prompt)
    src, prior = extract_program_with_prior(resp)
    if src.strip():
        cached.write_text(src + "\n---PRIOR---\n" + str(prior))
    return src, prior


def propose_dimension_locked_program(parent_src, parent_score, logs, branch: str,
                                     rich_template: str, target_dimension: str,
                                     cache_dir, caller=None) -> tuple[str, float]:
    """Expand with dimension-locking: exactly ONE tweak in target_dimension."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_dimension_locked_prompt(parent_src, parent_score, logs, branch, rich_template, target_dimension)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"atomic_{branch}_{target_dimension}_{key}.py"
    if cached.exists():
        text = cached.read_text()
        parts = text.split("\n---PRIOR---\n")
        if len(parts) == 2:
            return parts[0], float(parts[1])
        return text, 0.5
    resp = caller(prompt)
    src, prior = extract_program_with_prior(resp)
    if src.strip():
        cached.write_text(src + "\n---PRIOR---\n" + str(prior))
    return src, prior


def self_correct_program(parent_src, error_log, branch: str,
                         rich_template: str, cache_dir, caller=None) -> str:
    """When a candidate fails, ask the LLM to repair it."""
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_self_correct_prompt(parent_src, error_log, branch, rich_template)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"correct_{branch}_{key}.py"
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
