"""Sample weights (Lopez de Prado AFML ch.4) for overlapping-label FX data.

Our labels are forward returns over multi-bar/multi-day horizons, so consecutive
labels SHARE outcome bars (concurrency) and are not IID. This module computes:

  - concurrency     : # labels live at each bar
  - average uniqueness : per-label mean of 1/concurrency over its span
  - return-attribution weights : |sum over span of bar_return/concurrency|
  - time-decay weights : down-weight older observations (AFML getTimeDecay)
  - sequential bootstrap : draw low-overlap samples preferentially

Label span: bar i's label uses bars (i, e_i], where e_i = first bar >= t_i + H.

Self-test: `uv run python scripts/fx_coint/sample_weights.py`
"""
from __future__ import annotations

import numpy as np


def label_end_idx(ts_ns: np.ndarray, horizon_ns: int) -> np.ndarray:
    """e_i = first bar index with t >= t_i + horizon (wall-clock). Clipped to n-1;
    labels whose window runs off the end are flagged with e_i == i (invalid)."""
    n = len(ts_ns)
    e = np.searchsorted(ts_ns, ts_ns + horizon_ns, side="left")
    off_end = e >= n
    e = np.clip(e, 0, n - 1)
    e[off_end] = np.arange(n)[off_end]  # mark invalid (span length 1, dropped later)
    return e


def concurrency(n: int, end_idx: np.ndarray) -> np.ndarray:
    """co[t] = number of labels active at bar t (label i active over [i, e_i])."""
    delta = np.zeros(n + 1)
    np.add.at(delta, np.arange(n), 1.0)
    np.add.at(delta, end_idx + 1, -1.0)
    co = np.cumsum(delta[:n])
    return np.maximum(co, 1.0)


def average_uniqueness(start: np.ndarray, end_idx: np.ndarray, co: np.ndarray) -> np.ndarray:
    """u_i = mean_{t in [i, e_i]} 1/co[t]."""
    inv = 1.0 / co
    pref = np.concatenate([[0.0], np.cumsum(inv)])
    span = end_idx - start + 1
    return (pref[end_idx + 1] - pref[start]) / span


def return_attribution_weights(log_ret: np.ndarray, start: np.ndarray, end_idx: np.ndarray,
                               co: np.ndarray, normalize: bool = True) -> np.ndarray:
    """w_i = |sum_{t in (i, e_i]} r_t / co[t]| ; high-return, low-overlap => high weight."""
    contrib = log_ret / co
    pc = np.concatenate([[0.0], np.cumsum(contrib)])
    w = np.abs(pc[end_idx + 1] - pc[start + 1])
    if normalize and w.sum() > 0:
        w = w * len(w) / w.sum()
    return w


def time_decay(avg_u: np.ndarray, last_w: float = 1.0) -> np.ndarray:
    """AFML getTimeDecay on cumulative uniqueness (chronological order assumed).
    last_w in [0,1]: oldest weight = last_w, newest = 1, linear in cum-uniqueness.
    last_w < 0: oldest fraction gets 0 weight."""
    cum = np.cumsum(avg_u)
    cum = cum / cum[-1] if cum[-1] > 0 else cum
    if last_w >= 0:
        slope = (1.0 - last_w) / 1.0
        const = 1.0 - slope * 1.0
        dec = const + slope * cum  # = last_w at cum=0 ... 1 at cum=1
        dec = last_w + (1 - last_w) * cum
    else:
        slope = 1.0 / ((last_w + 1) * 1.0)
        const = 1.0 - slope * 1.0
        dec = const + slope * cum
        dec[dec < 0] = 0.0
    return dec


def concurrency_spans(n: int, start: np.ndarray, end_idx: np.ndarray) -> np.ndarray:
    """co[t] = #labels whose [start_i, end_i] covers bar t (explicit starts).

    Like concurrency() but with explicit per-label start bars instead of assuming
    one label per bar. Used for sampled event sets where labels may have non-
    consecutive starts.
    """
    delta = np.zeros(n + 1)
    np.add.at(delta, np.asarray(start), 1.0)
    np.add.at(delta, np.asarray(end_idx) + 1, -1.0)
    co = np.cumsum(delta[:n])
    return np.maximum(co, 1.0)


def event_weights(bar_log_ret: np.ndarray, entry: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """Return-attribution sample weights for a sampled event set on the bar timeline.

    Computes concurrency_spans for the event set (entry, t1), then delegates to
    return_attribution_weights for weight computation.

    Args:
        bar_log_ret: log returns per bar [t=0..n-1]
        entry: per-event entry bar indices
        t1: per-event end bar indices (inclusive)

    Returns:
        normalized sample weights [0..m-1]
    """
    co = concurrency_spans(len(bar_log_ret), entry, t1)
    return return_attribution_weights(bar_log_ret, np.asarray(entry), np.asarray(t1), co)


def seq_bootstrap(start: np.ndarray, end_idx: np.ndarray, n_draws: int | None = None,
                  rng: np.random.Generator | None = None) -> np.ndarray:
    """Sequential bootstrap (AFML): each draw's prob ∝ avg uniqueness given the
    already-drawn set. Reduces overlap vs standard bootstrap. O(m * n_draws * span)
    — intended for a manageable label subsample."""
    rng = rng or np.random.default_rng(0)
    m = len(start)
    n_draws = n_draws or m
    lo = int(start.min())
    hi = int(end_idx.max())
    cover = np.zeros(hi - lo + 2)  # how many drawn labels cover each bar
    drawn = []
    spans = [(int(s) - lo, int(e) - lo) for s, e in zip(start, end_idx)]
    for _ in range(n_draws):
        u = np.empty(m)
        for j, (s, e) in enumerate(spans):
            seg = cover[s:e + 1]
            u[j] = np.mean(1.0 / (seg + 1.0))
        p = u / u.sum()
        pick = rng.choice(m, p=p)
        drawn.append(pick)
        s, e = spans[pick]
        cover[s:e + 1] += 1.0
    return np.array(drawn)


def _self_test() -> None:
    # 5 bars, label horizon = 2 bars, regular spacing
    ts = np.arange(6, dtype="int64") * 60_000_000_000  # 1-min in ns
    H = 2 * 60_000_000_000
    e = label_end_idx(ts, H)
    print("end_idx:", e)  # expect [2,3,4,5,5,5]
    co = concurrency(len(ts), e)
    print("concurrency:", co)
    start = np.arange(len(ts))
    u = average_uniqueness(start, e, co)
    print("avg_uniqueness:", np.round(u, 3))
    print("effective N:", round(u[:-1].sum(), 2), "of raw", len(ts) - 1)
    r = np.array([0, 1.0, -2, 3, -1, 0.5])
    w = return_attribution_weights(r, start, e, co)
    print("return-attribution w:", np.round(w, 3))
    d = time_decay(u, last_w=0.5)
    print("time-decay (last_w=0.5):", np.round(d, 3))
    sub = slice(0, 4)
    sb = seq_bootstrap(start[sub], e[sub], n_draws=4)
    print("seq_bootstrap draws:", sb)
    print("self-test OK")


if __name__ == "__main__":
    _self_test()
