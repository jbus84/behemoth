from __future__ import annotations

import numpy as np
import pandas as pd


def deploy_gate(deploy_score: np.ndarray, q: float) -> np.ndarray:
    """Boolean mask: deploy on the top-q of the program's own finite scores."""
    s = np.asarray(deploy_score, float)
    finite = np.isfinite(s)
    if finite.sum() == 0:
        return np.zeros_like(s, dtype=bool)
    cut = np.nanquantile(s[finite], 1.0 - float(q))
    return finite & (s >= cut)


def simulate_bracket(*, k, close, high, low, spread, delta_pips, stop_pips,
                     max_hold, pip, commission_pips):
    """Two-sided maker bracket from bar k. Returns dict(filled, side, exit, net_pips)."""
    n = len(close)
    p = float(close[k])
    d = delta_pips * pip
    L, U = p - d, p + d
    lo_band = p - d - stop_pips * pip
    hi_band = p + d + stop_pips * pip
    end = min(n - 1, k + int(max_hold))

    side = 0
    entry_i = None
    entry_px = None
    for i in range(k + 1, end + 1):
        hit_buy = low[i] <= L
        hit_sell = high[i] >= U
        if hit_buy and hit_sell:
            return {"filled": False, "side": 0, "exit": "ambiguous", "net_pips": 0.0}
        if hit_buy:
            side, entry_i, entry_px = 1, i, L
            break
        if hit_sell:
            side, entry_i, entry_px = -1, i, U
            break
    if side == 0:
        return {"filled": False, "side": 0, "exit": "nofill", "net_pips": 0.0}

    tp = p  # center
    sl = lo_band if side == 1 else hi_band
    for i in range(entry_i, end + 1):
        if side == 1:
            hit_tp = high[i] >= tp
            hit_sl = low[i] <= sl
        else:
            hit_tp = low[i] <= tp
            hit_sl = high[i] >= sl
        if hit_sl:  # pessimistic: SL wins same-bar ties
            net = -stop_pips - float(spread[i]) - commission_pips
            return {"filled": True, "side": side, "exit": "sl", "net_pips": net}
        if hit_tp:
            net = delta_pips - commission_pips
            return {"filled": True, "side": side, "exit": "tp", "net_pips": net}
    gross = (close[end] - entry_px) / pip * side
    net = gross - float(spread[end]) - commission_pips
    return {"filled": True, "side": side, "exit": "timeout", "net_pips": net}


def evaluate_deploy(*, deploy_score, close, high, low, spread, cost, test_month,
                    q, delta_pips, stop_pips, max_hold, pip, commission_pips):
    """Run the bracket for every gated deploy bar; return DataFrame(net, test_month)."""
    gate = deploy_gate(deploy_score, q)
    nets, months = [], []
    for k in np.where(gate)[0]:
        r = simulate_bracket(
            k=int(k), close=close, high=high, low=low, spread=spread,
            delta_pips=delta_pips, stop_pips=stop_pips, max_hold=max_hold,
            pip=pip, commission_pips=commission_pips,
        )
        if not r["filled"]:
            continue
        nets.append(r["net_pips"])
        months.append(test_month[k])
    return pd.DataFrame({"net": np.asarray(nets, float),
                         "test_month": np.asarray(months)})


def deploy_diagnostics(*, deploy_score, close, high, low, spread, cost, test_month,
                       q, delta_pips, stop_pips, max_hold, pip, commission_pips):
    gate = deploy_gate(deploy_score, q)
    idx = np.where(gate)[0]
    n_deploy = len(idx)
    if n_deploy == 0:
        return {"deploy_rate": 0.0, "fill_rate": float("nan"), "tp_rate": float("nan"),
                "sl_rate": float("nan"), "timeout_rate": float("nan"),
                "mean_net": float("nan"), "month_hit_rate": float("nan")}
    fills = tps = sls = tos = 0
    nets, months = [], []
    for k in idx:
        r = simulate_bracket(
            k=int(k), close=close, high=high, low=low, spread=spread,
            delta_pips=delta_pips, stop_pips=stop_pips, max_hold=max_hold,
            pip=pip, commission_pips=commission_pips,
        )
        if not r["filled"]:
            continue
        fills += 1
        tps += r["exit"] == "tp"
        sls += r["exit"] == "sl"
        tos += r["exit"] == "timeout"
        nets.append(r["net_pips"])
        months.append(test_month[k])
    if fills == 0:
        return {"deploy_rate": n_deploy / len(close), "fill_rate": 0.0,
                "tp_rate": float("nan"), "sl_rate": float("nan"),
                "timeout_rate": float("nan"), "mean_net": float("nan"),
                "month_hit_rate": float("nan")}
    monthly = pd.Series(nets).groupby(np.asarray(months)).mean()
    return {
        "deploy_rate": n_deploy / len(close),
        "fill_rate": fills / n_deploy,
        "tp_rate": tps / fills,
        "sl_rate": sls / fills,
        "timeout_rate": tos / fills,
        "mean_net": float(np.mean(nets)),
        "month_hit_rate": float((monthly > 0).mean()),
    }
