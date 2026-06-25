"""State-based exit policy reading the causal RBPF posterior."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitPolicy:
    pi_exit: float = 0.4         # exit if P(trend) drops below this
    mu_floor_bps_z: float = 0.0  # exit if favorable drift decays past this


def exit_index(post: dict, side: str, max_hold: int) -> int:
    sign = 1.0 if side == "long" else -1.0
    p_trend = post["p_trend"]
    mu_hat = post["mu_hat"]
    n = min(max_hold, len(p_trend))
    pol = ExitPolicy()
    for t in range(n):
        favorable = sign * mu_hat[t]
        if p_trend[t] < pol.pi_exit:
            return t
        if favorable < 0:                      # drift flipped against the trade
            return t
        if favorable < pol.mu_floor_bps_z:     # favorable drift decayed away
            return t
    return n - 1
