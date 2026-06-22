"""Triple-barrier labeling (Lopez de Prado AFML ch.3).

For each event (entry bar) we set a vertical barrier (max holding, wall-clock) and
two symmetric horizontal barriers (+/- ptSl * target-vol). The label/outcome is the
return at the FIRST barrier touched (path-dependent), and t1 is when it is touched.

Symmetric horizontals + long side => first-touch time is side-independent (this is
the 'learn the side' setup, AFML 3.5). Returns the realized first-touch return so we
can correlate features against the path-dependent label.

Self-test: `uv run python scripts/fx_coint/triple_barrier.py`
"""
from __future__ import annotations

import numpy as np


def vertical_idx(ts_ns: np.ndarray, ev: np.ndarray, vert_ns: int) -> np.ndarray:
    n = len(ts_ns)
    v = np.searchsorted(ts_ns, ts_ns[ev] + vert_ns, side="left")
    v = np.clip(v, 0, n - 1)
    v = np.maximum(v, np.minimum(ev + 1, n - 1))  # at least 1 bar ahead
    return v


def triple_barrier(logp: np.ndarray, ts_ns: np.ndarray, ev: np.ndarray,
                   vert_ns: int, width: np.ndarray):
    """width[k] = horizontal half-width in log-return units for event ev[k] (>0).
    Returns: t1_idx, ret_bps (first-touch), hold_bars, touched (1=up,-1=dn,0=vert)."""
    vert = vertical_idx(ts_ns, ev, vert_ns)
    t1 = np.empty(len(ev), dtype=np.int64)
    ret = np.empty(len(ev))
    touched = np.zeros(len(ev), dtype=np.int8)
    for k in range(len(ev)):
        i = ev[k]
        ve = vert[k]
        path = logp[i + 1:ve + 1] - logp[i]
        w = width[k]
        up = np.argmax(path >= w) if np.any(path >= w) else -1
        dn = np.argmax(path <= -w) if np.any(path <= -w) else -1
        if up == -1 and dn == -1:
            j, tc = ve, 0
        elif dn == -1 or (up != -1 and up <= dn):
            j, tc = i + 1 + up, 1
        else:
            j, tc = i + 1 + dn, -1
        t1[k] = j
        ret[k] = (logp[j] - logp[i]) * 1e4
        touched[k] = tc
    return t1, ret, t1 - ev, touched


def _self_test() -> None:
    # monotone up path; symmetric barriers; should hit UP barrier early
    logp = np.log(np.array([100, 100.5, 101, 101.5, 102, 102.5], dtype=float))
    ts = np.arange(6, dtype="int64") * 60_000_000_000
    ev = np.array([0])
    width = np.array([0.012])  # ~1.2% -> hit around bar 3 (1.5% up)
    t1, ret, hold, tc = triple_barrier(logp, ts, ev, vert_ns=10 * 60_000_000_000, width=width)
    print("t1:", t1, "ret_bps:", np.round(ret, 1), "hold:", hold, "touched:", tc)
    assert tc[0] == 1 and t1[0] == 3, "expected up-touch at bar 3"
    print("self-test OK")


if __name__ == "__main__":
    _self_test()
