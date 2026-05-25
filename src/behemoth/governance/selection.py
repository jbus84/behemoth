"""Stage G2 selection gates."""

from __future__ import annotations

import pandas as pd


def apply_capacity_gate(
    *,
    states: pd.DataFrame,
    capacity_floor_monthly: float,
    capacity_floor_annual: float,
) -> pd.DataFrame:
    out = states.copy()
    out["capacity_pass"] = (
        out["avg_monthly_signals"].astype(float) >= float(capacity_floor_monthly)
    ) & (out["annualized_signals"].astype(float) >= float(capacity_floor_annual))
    out["capacity_pass"] = out["capacity_pass"].map(bool).astype(object)
    return out


def apply_stability_gate(
    *,
    state_monthly: pd.DataFrame,
    max_state_churn: float,
    max_top_state_share: float,
    max_state_hhi: float,
) -> pd.DataFrame:
    if state_monthly.empty:
        return pd.DataFrame(columns=["state_id", "stability_pass"])

    total_months = state_monthly["month"].nunique()
    per_state = (
        state_monthly.groupby("state_id", sort=False)
        .agg(
            avg_share=("share_of_signals", "mean"),
            months_present=("month", "nunique"),
        )
        .reset_index()
    )

    share = state_monthly["share_of_signals"].astype(float)
    hhi_per_month = (
        state_monthly.assign(_share_square=share * share)
        .groupby("month", sort=False)["_share_square"]
        .sum()
    )
    avg_hhi = float(hhi_per_month.mean()) if len(hhi_per_month) else 0.0

    per_state["churn"] = (
        1.0 - (per_state["months_present"].astype(float) / float(total_months))
        if total_months
        else 0.0
    )
    per_state["stability_pass"] = (
        (per_state["avg_share"].astype(float) <= float(max_top_state_share))
        & (per_state["churn"].astype(float) <= float(max_state_churn))
        & (avg_hhi <= float(max_state_hhi))
    )
    per_state["stability_pass"] = per_state["stability_pass"].map(bool).astype(object)
    return per_state[["state_id", "stability_pass"]]


def apply_family_selection_gate(
    *,
    candidates: pd.DataFrame,
    adapter,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    out = candidates.copy()
    out["selection_gate_pass"] = out.apply(
        lambda row: bool(adapter.selection_gate(row, thresholds)),
        axis=1,
    )
    out["selection_gate_pass"] = out["selection_gate_pass"].map(bool).astype(object)
    return out


def select_states_rolling(
    *,
    state_monthly: pd.DataFrame,
    adapter,
    thresholds: dict,
) -> pd.DataFrame:
    months_sorted = sorted(state_monthly["month"].astype(str).unique())
    train_window = int(thresholds["state_train_months"])
    rows: list[dict[str, object]] = []

    for i, month in enumerate(months_sorted):
        train_months = months_sorted[max(0, i - train_window) : i]
        month_state_ids = (
            state_monthly.loc[state_monthly["month"].astype(str) == month, "state_id"]
            .drop_duplicates()
            .tolist()
        )

        if len(train_months) < train_window:
            for state_id in month_state_ids:
                rows.append(
                    {
                        "state_id": state_id,
                        "month": month,
                        "train_months": ",".join(train_months),
                        "capacity_pass": False,
                        "stability_pass": False,
                        "selection_gate_pass": False,
                        "selected": False,
                    }
                )
            continue

        train = state_monthly[state_monthly["month"].astype(str).isin(train_months)].copy()
        agg = (
            train.groupby("state_id", sort=False)
            .agg(
                avg_monthly_signals=("monthly_signals", "mean"),
                mean_gross_pips=("mean_gross_pips", "mean"),
                both_window_rate=("both_window_rate", "mean"),
                p_up_first=("p_up_first", "mean"),
            )
            .reset_index()
        )
        agg["annualized_signals"] = agg["avg_monthly_signals"].astype(float) * 12.0

        cap = apply_capacity_gate(
            states=agg,
            capacity_floor_monthly=thresholds["capacity_floor_monthly"],
            capacity_floor_annual=thresholds["capacity_floor_annual"],
        )
        stab = apply_stability_gate(
            state_monthly=train,
            max_state_churn=thresholds["max_state_churn"],
            max_top_state_share=thresholds["max_top_state_share"],
            max_state_hhi=thresholds["max_state_hhi"],
        )
        merged = cap.merge(stab, on="state_id", how="left")
        merged["stability_pass"] = (
            merged["stability_pass"].fillna(False).map(bool).astype(object)
        )
        gated = apply_family_selection_gate(
            candidates=merged,
            adapter=adapter,
            thresholds=thresholds["selection_gates"],
        )
        gated["selected"] = (
            gated["capacity_pass"].astype(bool)
            & gated["stability_pass"].astype(bool)
            & gated["selection_gate_pass"].astype(bool)
        )

        max_states = int(thresholds.get("max_states", len(gated)))
        selected_idx = gated.index[gated["selected"]].tolist()
        if len(selected_idx) > max_states:
            keep_idx = set(
                gated.loc[selected_idx]
                .sort_values("mean_gross_pips", ascending=False)
                .head(max_states)
                .index
            )
            gated.loc[~gated.index.isin(keep_idx), "selected"] = False

        if int(thresholds.get("min_states", 0)) > int(gated["selected"].sum()):
            gated["selected"] = False

        emitted_state_ids = set(gated["state_id"].tolist())
        for _, row in gated.iterrows():
            rows.append(
                {
                    "state_id": row["state_id"],
                    "month": month,
                    "train_months": ",".join(train_months),
                    "capacity_pass": bool(row["capacity_pass"]),
                    "stability_pass": bool(row["stability_pass"]),
                    "selection_gate_pass": bool(row["selection_gate_pass"]),
                    "selected": bool(row["selected"]),
                }
            )
        for state_id in month_state_ids:
            if state_id in emitted_state_ids:
                continue
            rows.append(
                {
                    "state_id": state_id,
                    "month": month,
                    "train_months": ",".join(train_months),
                    "capacity_pass": False,
                    "stability_pass": False,
                    "selection_gate_pass": False,
                    "selected": False,
                }
            )

    out = pd.DataFrame(
        rows,
        columns=[
            "state_id",
            "month",
            "train_months",
            "capacity_pass",
            "stability_pass",
            "selection_gate_pass",
            "selected",
        ],
    )
    for col in ("capacity_pass", "stability_pass", "selection_gate_pass", "selected"):
        out[col] = out[col].map(bool).astype(object)
    return out
