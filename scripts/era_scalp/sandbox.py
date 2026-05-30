from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era.sandbox import _arrays_match, static_check
from scripts.era_scalp.context import FeatureContext

_WORKER = r"""
import sys, numpy as np
from scripts.era_scalp.context import FeatureContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
hour = payload["hour"]; hour = None if hour.size == 0 else hour
ctx = FeatureContext(X=payload["X"], names=list(payload["names"]), hour=hour)
fn = str(payload["fn"])
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns[fn](ctx), dtype=float).reshape(-1)
    if out.shape[0] != ctx.n_bars:
        raise ValueError(f"{fn} length {out.shape[0]} != n_bars {ctx.n_bars}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: FeatureContext, timeout: float = 10.0,
                required_fn: str = "signal"):
    """Return (output_array | None, error | None, logs). `required_fn` is the program
    entry-point name the sandbox requires and executes (e.g. 'signal' or 'deploy')."""
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
            fn=required_fn,
            X=ctx.X,
            names=np.array(ctx.names),
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


def causality_probe(src, ctx, clean_signal, n_cuts: int = 2, seed: int = 0,
                    required_fn: str = "signal"):
    """Reject programs whose past output depends on future bars."""
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_signal, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        X2 = ctx.X.copy()
        X2[k + 1 :, :] = rng.standard_normal(X2[k + 1 :, :].shape) * 10.0
        hour2 = None
        if ctx.hour is not None:
            hour2 = ctx.hour.copy()
            hour2[k + 1 :] = rng.integers(0, 24, size=hour2[k + 1 :].shape).astype(float)
        ctx2 = FeatureContext(X=X2, names=ctx.names, hour=hour2)
        sig2, err, _ = run_program(src, ctx2, timeout=10.0, required_fn=required_fn)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1], np.asarray(sig2, float)[: k + 1]):
            return False, f"non-causal: signal[:{k + 1}] changed when future bars perturbed"
    return True, "ok"
