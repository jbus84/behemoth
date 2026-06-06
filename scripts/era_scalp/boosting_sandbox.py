"""Sandbox for build_features(ctx) -> (n_bars, n_feat). Mirrors basket_sandbox but for
variable-width 2-D feature output over FeatureContext. np-only; causality-probed."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era.sandbox import _arrays_match, static_check as _static_check
from scripts.era_scalp.context import FeatureContext


def static_check(src: str, required_fn: str = "build_features"):
    return _static_check(src, required_fn=required_fn)


_WORKER = r"""
import sys, numpy as np
from scripts.era_scalp.context import FeatureContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
hour = payload["hour"]; hour = None if hour.size == 0 else hour
ctx = FeatureContext(X=payload["X"], names=list(payload["names"]), hour=hour)
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns["build_features"](ctx), dtype=float)
    if out.ndim != 2 or out.shape[0] != ctx.n_bars:
        raise ValueError(f"build_features shape {out.shape} != (n_bars, n_feat) rows {ctx.n_bars}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: FeatureContext, timeout: float = 10.0,
                required_fn: str = "build_features"):
    ok, reason = static_check(src, required_fn=required_fn)
    if not ok:
        return None, f"static_check: {reason}", ""
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.npz"
        out = Path(d) / "out.npy"
        wrk = Path(d) / "w.py"
        np.savez(inp, src=src, X=ctx.X, names=np.array(ctx.names),
                 hour=ctx.hour if ctx.hour is not None else np.array([]))
        wrk.write_text(_WORKER)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            proc = subprocess.run([sys.executable, str(wrk), str(inp), str(out)],
                                  capture_output=True, text=True, timeout=timeout,
                                  cwd=str(Path.cwd()), env=env)
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs


def causality_probe(src, ctx, clean_feats, n_cuts: int = 4, seed: int = 0,
                    required_fn: str = "build_features", nan_frac: float = 0.3):
    """Reject feature code whose past rows depend on future rows. Perturbs rows > k and
    requires feats[:k+1, :] unchanged."""
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_feats, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        X2 = ctx.X.copy()
        fut = X2[k + 1:, :]
        fut[:] = rng.standard_normal(fut.shape) * 10.0
        if fut.size:
            fut[rng.random(fut.shape) < nan_frac] = np.nan
        X2[k + 1:, :] = fut
        ctx2 = FeatureContext(X=X2, names=ctx.names, hour=ctx.hour)
        f2, err, _ = run_program(src, ctx2, required_fn=required_fn)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1, :], np.asarray(f2, float)[: k + 1, :]):
            return False, f"non-causal: feats[:{k + 1}] changed when future perturbed"
    return True, "ok"
