import pandas as pd


def apply_loss_streak_guardrail(
    df: pd.DataFrame,
    loss_threshold: float = 0.0,
    loss_streak: int = 3,
    cooldown_days: int = 7,
    return_skipped: bool = False,
):
    """
    Apply loss-streak cooldown guardrail by pair.
    Expects df to contain columns: pair, exit_ts, pnl_bps.
    """
    df = df.sort_values("exit_ts").copy()
    keep = []
    skipped = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=cooldown_days).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(row.exit_ts)
        pnl = float(row.pnl_bps)

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            skipped.append(row)
            continue

        keep.append(row)

        if pnl > loss_threshold:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= loss_streak:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    kept_df = pd.DataFrame(keep) if keep else df.iloc[:0]
    if return_skipped:
        skipped_df = pd.DataFrame(skipped) if skipped else df.iloc[:0]
        return kept_df, skipped_df
    return kept_df
