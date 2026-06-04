from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era.context import CrossSectionContext

_FORBIDDEN_NAMES = {
    "open",
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
    "vars",
    "input",
}


def static_check(src: str, required_fn: str = "residual") -> tuple[bool, str]:
    """Reject imports, dunder access, and dangerous builtins. Require required_fn()."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    has_residual = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "imports are not allowed"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"dunder attribute access not allowed: {node.attr}"
        # Forbid np.random.* — a program using it is non-deterministic (not
        # reproducible live) and can defeat the causality probe (its past output
        # varies run-to-run independent of the future perturbation).
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
            has_residual = True
    if not has_residual:
        return False, f"must define {required_fn}(ctx)"
    return True, "ok"


# Worker source: runs in a subprocess, reconstructs ctx, execs the program.
_WORKER = r"""
import sys, json, numpy as np
from scripts.era.context import CrossSectionContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
hour = payload["hour"]; hour = None if hour.size == 0 else hour
ctx = CrossSectionContext(r=payload["r"], names=list(payload["names"]),
                          target=str(payload["target"]), usd_sign=int(payload["usd_sign"]),
                          hour=hour)
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns["residual"](ctx), dtype=float).reshape(-1)
    if out.shape[0] != ctx.n_bars:
        raise ValueError(f"residual length {out.shape[0]} != n_bars {ctx.n_bars}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: CrossSectionContext, timeout: float = 10.0):
    """Return (residual_array | None, error | None, logs)."""
    ok, reason = static_check(src)
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
            target=ctx.target,
            usd_sign=ctx.usd_sign,
            hour=ctx.hour if ctx.hour is not None else np.array([]),
        )
        wrk.write_text(_WORKER)
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [sys.executable, str(wrk), str(inp), str(out)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path.cwd()),
                env=env,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs


def _arrays_match(a: np.ndarray, b: np.ndarray) -> bool:
    """Equal where both finite (allclose) and NaN in identical positions."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = np.isnan(a), np.isnan(b)
    if not np.array_equal(na, nb):
        return False
    fa, fb = a[~na], b[~nb]
    return bool(np.allclose(fa, fb, rtol=1e-9, atol=1e-9))


def causality_probe(src, ctx, clean_resid, n_cuts: int = 5, seed: int = 0,
                    nan_frac: float = 0.3):
    """Reject programs whose past residual depends on future bars.

    For each of `n_cuts` interior cut points k, every row at index > k is
    replaced with large finite noise AND a `nan_frac` fraction of those future
    rows are set to NaN, then the program is re-run and residual[:k+1] is
    required to be unchanged vs the clean run. Any op that reads future rows
    (forward indexing, centered windows, full-split statistics, or future
    NaN-pattern counts) perturbs a past value and is rejected. Returns (ok, reason).
    """
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_resid, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        r2 = ctx.r.copy()
        fut = r2[k + 1 :, :]
        fut[:] = rng.standard_normal(fut.shape) * 10.0
        if fut.size:
            fut[rng.random(fut.shape) < nan_frac] = np.nan
        r2[k + 1 :, :] = fut
        hour2 = None
        if ctx.hour is not None:
            hour2 = ctx.hour.copy()
            hour2[k + 1 :] = rng.integers(0, 24, size=hour2[k + 1 :].shape).astype(float)
        ctx2 = CrossSectionContext(
            r=r2, names=ctx.names, target=ctx.target, usd_sign=ctx.usd_sign, hour=hour2
        )
        resid2, err, _ = run_program(src, ctx2, timeout=10.0)
        if err is not None:
            return (
                False,
                f"non-causal: errors under future perturbation at k={k}: {err}",
            )
        if not _arrays_match(clean[: k + 1], np.asarray(resid2, float)[: k + 1]):
            return (
                False,
                f"non-causal: residual[:{k + 1}] changed when future bars perturbed",
            )
    return True, "ok"
