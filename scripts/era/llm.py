from __future__ import annotations
import hashlib, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_RULES = (
    "You write a Python function `residual(ctx) -> np.ndarray`.\n"
    "ctx gives ONLY causal cross-section data: ctx.r (n_bars x 6 USD-aligned\n"
    "vol-normalised returns), ctx.target_col(), ctx.peers(), ctx.target_idx,\n"
    "ctx.names, ctx.usd_sign. `np` is available. You CANNOT import anything and\n"
    "CANNOT access future returns / y_fwd / labels (they are not in ctx).\n"
    "Return a per-bar residual; larger |residual| == stronger idiosyncratic\n"
    "dislocation of the target. Output ONLY one ```python code block.\n"
)

def build_prompt(parent_src: str, parent_score: float, logs: str, idea: str) -> str:
    return (
        "Improve this dispersion residual program to increase its score.\n\n"
        f"{_RULES}\n"
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
    out = subprocess.run([str(ROOT / "scripts/cheap_llm.sh"), prompt],
                         capture_output=True, text=True, timeout=180)
    return out.stdout

def propose_program(parent_src, parent_score, logs, idea, cache_dir, caller=None):
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(parent_src, parent_score, logs, idea)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"{key}.py"
    if cached.exists():
        return cached.read_text()
    src = extract_program(caller(prompt))
    cached.write_text(src)
    return src
