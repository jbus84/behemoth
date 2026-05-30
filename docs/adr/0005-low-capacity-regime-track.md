# ADR 0005: Low-Capacity Regime-Specific Strategy Track

- Status: Accepted (2026-05-30; evaluation harness merged in PR #273, decision target PASSed — see Evidence; transition work tracked in the follow-on plan)
- Date: 2026-05-30

## Context

The tick-opportunity governance pipeline gates every candidate state on a **capacity floor**: Stage 2 mining requires `min_annual_fills=5000`, and Stage 5 reduced-core (`scripts/select_reduced_core_regimes.py`, `capacity_pass_monthly_or_annual` ~line 989) requires `avg_month_rows >= 3000 OR annualized >= 3000`. The floor exists to guarantee a deployable state fires often enough to matter and to keep per-state estimates statistically stable.

A diagnostic over the 2026-05 multi-family trial's post-CatBoost WFO predictions (the `selected_exec` events, net of per-event `cost_est_pips`, conservative per-trade LB95 = mean − 1.645·std/√n) found that the floor is **selecting against the only profitable edge in the book**:

- Across all 6 symbols, the directional-library states that clear a conservative net-of-cost LB95 bar are **low-frequency, regime-specific** states — `ny_overlap` (UTC 13:00–16:59), `high_activity`, `high_range` regimes, at coarse 1000–2000-tick bars, horizon h3 (the `directional_inverse` family carries almost all of it).
- These states **all fail the capacity floor purely on frequency** — they fire far below 3000 rows/month.
- The states that **do** pass the capacity floor are net-**negative** after cost: at high frequency the per-trade move cannot overcome the ~0.46-pip cost / ~0.37-pip spread.

The current pipeline therefore deploys the losers and discards the winners. The mining `mean_gross_pips_*` columns do not reveal this because they are bid-to-bid (spread-optimistic) and pre-CatBoost — not tradeable P&L.

## Decision

Build an **evaluation harness** (`scripts/evaluate_low_capacity_track.py`, merged in PR #273) that scores each state on **robustness instead of raw capacity**, and use its portfolio readout as the evidence gate for whether to promote a parallel low-frequency track into governance.

Per state (grouped by `symbol, family, bar_ticks, state_id`), over `selected_exec` events net of per-event `cost_est_pips`, the harness computes: `n`, annualized fills, `avg_month_rows`, net mean, net LB95, positive-month share, and a one-sided t-test p-value. It then applies:

- **capacity gate** (the existing floor): `annualized >= 3000 OR avg_month_rows >= 3000`
- **low-frequency robustness gate**: `net_lb95 > 0 AND positive_month_share >= 0.6 AND n >= 200`
- **admitted** = robustness gate passes AND capacity gate fails (i.e. the states the floor currently drops)
- **Benjamini–Hochberg** FDR correction (q=0.10) across all tested states, to confirm admitted states survive multiple-testing.

Admitted states are aggregated into a combined low-frequency portfolio (pooled net LB95, portfolio positive-month share, monthly Sharpe, trades/year), compared against the capacity-passing baseline.

**Decision target:** promote a governed low-frequency track only if the admitted portfolio shows `net_lb95 > 0 AND positive_month_share >= 0.6`, robust to BH filtering.

## Consequences

- The 2026-05 trial evidence (below) **passes the decision target** and contradicts the floor: the admitted low-frequency book is conservatively profitable while the capacity-passing baseline loses money. Full numbers are persisted at `docs/analysis/low_capacity_track_2026-05_trial_report.md`.
- Promotion is **not automatic**. It requires the follow-on work in `docs/superpowers/plans/2026-05-30-directional-family-freeze-and-lowcap-gating.md`: the production freeze pipeline currently has **no path to deploy these states** — it only handles `oco_first_touch` (which is Stage-5 FAIL on all 6 symbols, so the 2026-05 freeze produced 0 locks), and the directional families where the edge lives have no model-export/freeze path.
- The admitted set is **small and concentrated** (5 states, 2 symbols, 1 family, ~1,447 trades/year). It is a real but low-capacity edge; sizing and portfolio-diversification expectations must be set accordingly.
- The capacity floor is config-tunable; this ADR does not delete it. The proposed track runs **alongside** the floor with robustness-based admission, so high-frequency capacity-passing states and low-frequency robust states are governed by separate, explicit gates.

## Evidence (2026-05 multi-family trial)

Harness run over the trial's directional predictions (`directional, directional_inverse, directional_run`), per-event cost from `tick_velocity`, gates as configured above (capacity_floor=3000, min_trades=200, min_positive_month_share=0.6, BH q=0.10). 1,745 states tested.

Per-symbol:

| Symbol | Directional States | Net-LB95-Positive | Capacity-Pass | Admitted | Admitted (BH) |
|---|---|---|---|---|---|
| EURUSD | 258 | 3 | 8 | 2 | 2 |
| GBPUSD | 292 | 4 | 11 | 3 | 3 |
| USDJPY | 309 | 0 | 16 | 0 | 0 |
| USDCHF | 277 | 1 | 9 | 0 | 0 |
| AUDUSD | 313 | 0 | 3 | 0 | 0 |
| USDCAD | 296 | 0 | 8 | 0 | 0 |

Portfolios (net of per-event cost):

| Portfolio | Net Mean | Net LB95 | Positive-Month Share | Trades/Year | Monthly Sharpe | States | Symbols | Families |
|---|---|---|---|---|---|---|---|---|
| Admitted (raw) | 1.549 | 0.918 | 80.0% | 1,447 | 0.574 | 5 | 2 | 1 |
| Admitted (BH-filtered) | 1.549 | 0.918 | 80.0% | 1,447 | 0.574 | 5 | 2 | 1 |
| Capacity-passing (baseline) | −0.877 | −0.898 | 0.0% | 187,518 | −4.852 | 55 | 6 | 1 |

Top admitted states by net LB95: EURUSD `directional_inverse__high_activity__h3` @1000 (LB95 +0.389, +month 69%, n=394); GBPUSD `directional_inverse__low_cost_q30_and_high_range_q70__h3` @2000 (+0.203, 83%, n=228); GBPUSD `directional_inverse__high_range_q70__h3` @2000 (+0.133, 71%, n=443); GBPUSD `directional_inverse__high_range_q80__h3` @2000 (+0.068, 78%, n=430); EURUSD `directional_inverse__ny_overlap__h3` @1000 (+0.028, 85%, n=314).

**Decision readout: PASS** (both raw and BH-filtered admitted portfolios: net_lb95 > 0 = True, positive_month_share ≥ 0.6 = True). The BH-filtered set is identical to the raw set — admitted states survive multiple-testing correction.
