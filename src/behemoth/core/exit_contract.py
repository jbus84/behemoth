from __future__ import annotations

from dataclasses import dataclass

from behemoth.core.timeout_policy import compute_max_hold_bars


@dataclass(frozen=True)
class ExitContract:
    mode: str
    variant: str
    max_hold_bars: int
    cross_zero_buffer_abs_z: float
    stop_win_level_abs_z: float
    use_stop_win: bool


def build_exit_contract(
    timeframe: str,
    entry_z: float,
    timeout_mode: str,
    variant: str,
    z_stop: float,
) -> ExitContract:
    abs_entry_z = abs(float(entry_z))
    max_hold_bars = compute_max_hold_bars(timeframe=timeframe, abs_entry_z=abs_entry_z, mode=timeout_mode)

    v = variant.strip().lower()
    if v == "baseline":
        return ExitContract(
            mode=timeout_mode,
            variant=v,
            max_hold_bars=max_hold_bars,
            cross_zero_buffer_abs_z=0.0,
            stop_win_level_abs_z=float(z_stop),
            use_stop_win=True,
        )
    if v == "soft_cross":
        return ExitContract(
            mode=timeout_mode,
            variant=v,
            max_hold_bars=max_hold_bars,
            cross_zero_buffer_abs_z=0.15,
            stop_win_level_abs_z=float(z_stop),
            use_stop_win=True,
        )
    if v == "no_stop_win":
        return ExitContract(
            mode=timeout_mode,
            variant=v,
            max_hold_bars=max_hold_bars,
            cross_zero_buffer_abs_z=0.0,
            stop_win_level_abs_z=float(z_stop),
            use_stop_win=False,
        )
    raise ValueError(f"Unsupported entry-time exit variant: {variant}")
