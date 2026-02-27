# MOM Loss-Limiter WFO Findings

Date: 2026-02-07

## Summary
We tested rule-based per-symbol loss limiters to reduce drawdown for MOM trades (M15, 2018–2025, cost-free). The best-performing family is a **loss-streak limiter**. We validated it with **rolling walk‑forward optimization (WFO)** to reduce overfitting risk.

Key outcome: **loss‑streak >= 3 with a cooldown of 7–14 days is robust out‑of‑sample**, consistently cutting drawdown while improving per‑trade mean returns.

## Guardrail Definition (Loss‑Streak)
- Track consecutive losing trades per symbol.
- If the loss streak reaches threshold `N`, pause that symbol for `cooldown` (time‑based).
- State is maintained per symbol across the full series.

## WFO Setup
Selection metric: `sharpe_trade` on training window.

WFO windows:
- Train 2018–2021 → Test 2022
- Train 2019–2022 → Test 2023
- Train 2020–2023 → Test 2024
- Train 2021–2024 → Test 2025

### WFO Results (selected rule → test year)
| Train | Test | Best Params | Test Trades | Test Mean (bps) | Test Total (bps) | Test Max DD (bps) | Test Sharpe (daily) | Test Sharpe (active) | Test Sharpe (trade) | Baseline Test Mean | Baseline Test Max DD |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2018–2021 | 2022 | streak=3, cooldown=7d | 5,237 | 43.96 | 230,202 | -4,344 | 5.17 | 5.92 | 20.88 | 6.58 | -21,321 |
| 2019–2022 | 2023 | streak=3, cooldown=7d | 4,231 | 47.93 | 202,780 | -3,669 | 2.93 | 3.40 | 7.12 | 10.95 | -23,349 |
| 2020–2023 | 2024 | streak=3, cooldown=14d | 3,532 | 30.36 | 107,223 | -3,076 | 4.59 | 5.30 | 14.65 | 0.32 | -34,719 |
| 2021–2024 | 2025 | streak=3, cooldown=14d | 3,489 | 32.53 | 113,489 | -4,138 | 4.01 | 4.78 | 14.79 | 3.12 | -32,791 |

## Recommended Rule (current best)
**Loss‑streak >= 3, cooldown 14 days (time‑based)**

This is the most stable across WFO folds and yields a large DD reduction vs baseline.

## Metric Definitions
We report three Sharpe measures:
- `sharpe` = daily aggregated PnL with **zero‑fill** for inactive days.
- `sharpe_active` = daily aggregated PnL for **active days only**.
- `sharpe_trade` = trade‑level Sharpe, annualized by trades/day.

These help avoid misleadingly low Sharpe when guardrails reduce trade frequency.

## Evidence Files
- WFO results: `data/analysis/mom_loss_limiter_wfo.csv`
- Sweep results: `data/analysis/mom_loss_limiter_sweep.csv`
- Combo results: `data/analysis/mom_loss_limiter_combos.csv`
- WFO script: `scripts/wfo_mom_loss_streak.py`
- Sweep scripts: `scripts/explore_mom_loss_limiters.py`, `scripts/explore_mom_loss_limiter_combos.py`
- Sharpe utilities: `scripts/metrics.py`
