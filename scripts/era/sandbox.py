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


def static_check(src: str) -> tuple[bool, str]:
    """Reject imports, dunder access, and dangerous builtins. Require residual()."""
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
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return False, f"forbidden name: {node.id}"
        if isinstance(node, ast.FunctionDef) and node.name == "residual":
            has_residual = True
    if not has_residual:
        return False, "must define residual(ctx)"
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
