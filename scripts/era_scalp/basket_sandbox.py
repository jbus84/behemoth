from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era_scalp.basket_context import BasketContext

_FORBIDDEN_NAMES = {"open", "eval", "exec", "compile", "globals", "locals",
                    "vars", "getattr", "setattr", "delattr", "__import__", "input"}


def static_check(src: str, required_fn: str = "score") -> tuple[bool, str]:
    """Reject imports, dunder access, np.random, dangerous builtins. Require score(ctx)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    has_fn = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "imports are not allowed"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"dunder attribute access not allowed: {node.attr}"
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "random"
            and isinstance(node.value, ast.Name)
            and node.value.id == "np"
        ):
            return False, "np.random is not allowed (non-deterministic)"
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return False, f"forbidden name: {node.id}"
        if isinstance(node, ast.FunctionDef) and node.name == required_fn:
            has_fn = True
    if not has_fn:
        return False, f"must define {required_fn}(ctx)"
    return True, "ok"


_WORKER = r"""
import sys, numpy as np
from scripts.era_scalp.basket_context import BasketContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
hour = payload["hour"]; hour = None if hour.size == 0 else hour
ctx = BasketContext(r=payload["r"], names=list(payload["names"]), hour=hour)
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns["score"](ctx), dtype=float)
    if out.shape != (ctx.n_bars, ctx.n_sym):
        raise ValueError(f"score shape {out.shape} != (n_bars, n_sym) {(ctx.n_bars, ctx.n_sym)}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: BasketContext, timeout: float = 10.0, required_fn: str = "score"):
    """Return (score_2d | None, error | None, logs)."""
    ok, reason = static_check(src, required_fn=required_fn)
    if not ok:
        return None, f"static_check: {reason}", ""
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.npz"
        out = Path(d) / "out.npy"
        wrk = Path(d) / "w.py"
        np.savez(
            inp,
            src=src,
            r=ctx.r,
            names=np.array(ctx.names),
            hour=ctx.hour if ctx.hour is not None else np.array([]),
        )
        wrk.write_text(_WORKER)
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [sys.executable, str(wrk), str(inp), str(out)],
                capture_output=True, text=True, timeout=timeout,
                cwd=str(Path.cwd()), env=env,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs


def _arrays_match(a: np.ndarray, b: np.ndarray) -> bool:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = np.isnan(a), np.isnan(b)
    if not np.array_equal(na, nb):
        return False
    return bool(np.allclose(a[~na], b[~nb], rtol=1e-9, atol=1e-9))


def causality_probe(src, ctx, clean_score, n_cuts: int = 5, seed: int = 0,
                    required_fn: str = "score", nan_frac: float = 0.3):
    """Reject programs whose past scores depend on future bars.

    For each interior cut k, rows > k are replaced with large finite noise (and a
    nan_frac fraction set to NaN); the program is re-run and score[:k+1, :] must be
    unchanged vs the clean run."""
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_score, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        r2 = ctx.r.copy()
        fut = r2[k + 1:, :]
        fut[:] = rng.standard_normal(fut.shape) * 10.0
        if fut.size:
            fut[rng.random(fut.shape) < nan_frac] = np.nan
        r2[k + 1:, :] = fut
        hour2 = None
        if ctx.hour is not None:
            hour2 = ctx.hour.copy()
            hour2[k + 1:] = rng.integers(0, 24, size=hour2[k + 1:].shape).astype(float)
        ctx2 = BasketContext(r=r2, names=ctx.names, hour=hour2)
        score2, err, _ = run_program(src, ctx2, timeout=10.0, required_fn=required_fn)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1, :], np.asarray(score2, float)[: k + 1, :]):
            return False, f"non-causal: score[:{k + 1}] changed when future bars perturbed"
    return True, "ok"
