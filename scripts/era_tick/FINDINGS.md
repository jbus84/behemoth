# Tick-by-tick assessor — Day-1 findings

Branch: `worktree-tick-by-tick-prototype`. Package: `scripts/era_tick/`.

## What was built

A genuine continuous-time tape reader (not bar aggregation): streaming raw-tick replay
(`tick_replay`) → constant-velocity **Kalman micro-price** (`micro_price`) → per-tick
**regime** + **extremum** detection (`regime`, `extrema`) → swappable **`TickPolicy`**
(`policy`) → **`TickEngine`** state machine with **tick-exact fills** (buy@ask / sell@bid,
`fill_model`) → gross/cost/net **metrics**, **viz**, and a `run_day1` CLI. 12 tests pass,
including the **look-ahead guard** (`test_engine_causality`: prefix decisions ≡ full-run
decisions — the engine cannot see the future).

The `TickPolicy.decide(state) -> Action` contract is the exact shape the ERA PUCT writer
would fill in, so Phase 2 is a `RunSpec` wrapper, not a new search loop. **Phase 2 was not
built** — the go/no-go gate failed (below).

## Result — EURUSD, raw Dukascopy ticks, 07:00–17:00 UTC

Naive fade on the Day-1 sample (2024-04-10, US CPI day): **NO-GO**.

| scenario | n | gross/trade | cost/trade | net/trade | hit | t |
|---|---|---|---|---|---|---|
| raw_dukascopy | 746 | **−0.029p** | 0.222p | −0.250p | 0.151 | −12.2 |
| retail +0.5p | 746 | −0.029p | 0.722p | −0.750p | 0.084 | −36.5 |

Gross is **negative before any cost** — fading micro-extensions is the wrong sign.

## The informative part — fade vs momentum, 5 CPI days

Mirror-image probe (`probe_sign_days.py`), gross **before cost**:

| policy | mean gross/trade | sign of days |
|---|---|---|
| fade | −0.009p | mixed (noise) |
| **momentum** | **+0.070p** | positive 4 / 5 |

There **is** signed intrabar structure: at the 1–10-tick scale micro-extensions
**continue** (momentum), they do not revert. But the amplitude is **~0.07p gross**, which
is **≈3× below raw Dukascopy round-trip cost (~0.22p)** and **~10× below retail (~0.7p)**.
Net is negative under every cost scenario.

## Iteration 2 — be selective, then ride (the "better decision per tick")

The naive policies traded ~constantly (700+/day, ~10-tick holds) for a tiny per-trade mean.
Two fixes, both motivated by "only act when confident, and don't bail instantly":

1. **Confidence gate from the Kalman itself**: `drift_t = drift_hat / sqrt(Var(drift))` —
   the filter's t-stat on the trend. Enter only when `|drift_t|` is high AND the regime is
   **DRIFT** (enter *with* the trend; the first momentum probe mistakenly traded in REVERT).
2. **Hysteresis ride**: exit only on a *confident reversal* / trailing give-back / stop —
   ride through ordinary pullbacks instead of scalping a fixed 2p (`exp_confident_momentum.py`).

This 20–40× cut trade count, lengthened holds from ~8 to ~100+ ticks, and lifted gross.
But it is **regime-conditional** — the split below is the headline:

| day_set | enter_t | trades/day | gross/trade | net/trade | gross/cost | avg_hold |
|---|---|---|---|---|---|---|
| **event** (CPI/FOMC) | 3.0 | 27.8 | **+0.269p** | **+0.060p** | 1.22× | 116 |
| event | 5.0 | 17.8 | +0.262p | +0.003p | 1.19× | 93 |
| **ordinary** | 3.0 | 17.0 | −0.038p | −0.185p | −0.17× | 158 |
| ordinary | 5.0 | 8.7 | +0.035p | −0.123p | 0.16× | 168 |

On trending (US-data) days the ridden momentum **clears raw cost and is net-positive**. On
ordinary days the edge **evaporates** (gross ≈ 0, net negative): the DRIFT detector still
fires on transient mini-trends in chop that then reverse.

## Iteration 3 — regime router on a broad, unbiased sample (the decisive test)

Hypothesis (user): the CatBoost/regime machinery need not be profitable — just tell us early
whether a day is trending, then route momentum (trend) vs fade/flat (chop). Tested causally
on **~109 weekdays, Mar–Jul 2024** (`exp_regime_router.py`): classify each day from its
**morning** (07:00–09:00 realized range + directionality, the day-level analogue of the
repo's `high_range_q70/q80` gates), trade the **afternoon out-of-sample** (09:00–17:00).

Result — **the hypothesis is not supported**:

- **No predictability**: `corr(morning_range, momentum_net) = −0.013`,
  `corr(morning_dir, momentum_net) = −0.079` ≈ 0. A trending morning does not forecast a
  tradable afternoon — intraday trendiness does not persist.
- **Broad-sample momentum is net-negative**: `always_mom = −45p` over 109 days (~−0.4p/day).
  The iter-2 event-day positivity was **selection bias** (CPI/FOMC days trend by construction).
- **Router fails**: routing chop days to fade is catastrophic (`always_fade = −3530p`, ~−32p/day);
  the blended router nets −1500 to −1700p. Fade is a uniform loser — it cannot be the chop leg.
- Faint consolation only: a high-morning-range gate cuts loss to ~break-even on the trend half
  (`mom_on_trend −2.2` / `mom_on_chop −42.8`) — it *avoids* the worst days but *finds* no winners.

## Verdict

**NO-GO.** Three independent walls, now established on unbiased samples:

1. **Trend is not predictable at the granularity we can trade** (morning→afternoon corr ≈ 0).
   So the "classify regime, switch model" router has no signal to act on.
2. **The base edge was event-day selection bias** — broad-sample momentum is net-negative even
   at raw Dukascopy cost.
3. **Retail cost wall** sits far above any gross seen (`project_retail_fx_edge_cost_wall`).
   Fade is uniformly negative, so there is no second regime-leg to route to.

The infrastructure is sound and look-ahead-guarded — the *signal* is the problem, not the code.
Phase-2 ERA-PUCT is **not justified**: a policy search optimises decision timing, but here the
binding constraints are signal amplitude and regime *predictability*, neither of which a search
over `TickPolicy` programs can manufacture. Consistent with the repo-wide cost-wall finding.

## Iteration 4 — "invert the fade?" (the −3530p is cost, not signal)

Fade's −3530p net over 109 afternoons looked like a huge invertible loss. Decomposed
(`exp_invert_fade.py`): **21,569 trades, gross +429.6p, cost 3,959.6p, net −3,530.1p**. Fade's
gross is *positive* — it is not on the wrong side; the loss is pure overtrading cost (~198
trades/day). Therefore:

- **Sign-flip**: `-net - 2*cost = −4,389p` — worse (flips the small +gross to −, pays cost twice).
- **Inverted-entry** (momentum entries, fade exits, real run): gross **+2,083.8p** (~5× fade's),
  cost 3,077p, **net −993.5p** — momentum is the right sign again, but ~166 trades/day still buried.

Same wall: per-trade gross ~0.10–0.12p < cost ~0.17–0.22p. The big number was the spread paid
21k times, not directional error. No invertible edge.

## Iteration 5 — ERA-PUCT harness + cross-symbol seed board (the rare-big-ride test)

Built the tick-domain ERA integration (`era_panel.py` causal feature panel, `era_exec.py`
streaming `score_frame` with **min-DAYS** anti-mirage floor, `era_seeds.py` 5 momentum seeds,
`run_era_tick.py`). Plugs into the proven `run_era_search`/`score_program` with the sandbox
causality probe. Judge = **day-robust LB** (`mean_day_net − z·SE`) so a low-frequency edge must
be consistent across many days, not concentrated on a lucky few — the explicit fix for the
"trade rarely, catch the big rides" thesis.

Seed-only cross-symbol (20 days, best seed per symbol), day-robust LB:

| symbol | best seed | gross/t | cost/t | net/t | day_lb |
|---|---|---|---|---|---|
| EURUSD | drift_eff | 0.055 | 0.21 | −0.15 | **−0.17** |
| USDJPY | residual_cont | 0.196 | 0.43 | −0.24 | −0.39 |
| GBPUSD | drift_eff | 0.111 | 0.68 | −0.57 | −0.58 |
| USDCHF | drift_eff | 0.087 | 0.93 | −0.84 | −0.87 |
| AUDUSD | drift_eff | 0.068 | 0.97 | −0.90 | −0.99 |
| USDCAD | drift_eff | 0.147 | 1.13 | −0.99 | −1.07 |

- **The USDCAD 8× mirage is destroyed**: forced to a meaningful sample (1171 trades), gross/trade
  collapses 6.05p → 0.147p; it is the *worst* net. Confirms the tiny-sample diagnosis.
- **"More trending pair" backfires**: gross is ~0.1p everywhere, but the trending majors carry
  3–5× wider spreads (cost 0.9–1.1p) that more than eat their bigger moves. EURUSD (tightest cost
  0.21p) is the *least*-negative. So the cost wall, not the move size, is binding.
- Every symbol × every seed = **negative day-robust LB**. The momentum signal family is sub-cost
  cross-symbol under an honest multi-day judge.

### Budgeted qwen search (EURUSD, budget 40, val 20d / holdout 40d)

A wiring bug masked the first attempt: the worktree had no `.env`, so `cheap_llm.sh` aborted
("OLLAMA_API_KEY not set") and every expansion returned empty — only the 5 seeds scored. Fixed
by symlinking the root `.env` into the worktree (gitignored). Re-run: **45 programs, 36
admissible** (31 qwen-generated valid signals). Outcome:

- **Nothing beat the seeds**; best val day-robust LB is still the `drift_eff` seed at −0.198.
- **No program — generated or seed — has a positive day-robust LB** on val or the 40-day holdout
  (best holdout LB −0.112). A couple show a faint positive *mean* net/trade (accel_confirm
  +0.05p) but it is within day-to-day noise; gross/trade ~0.1p vs cost ~0.2p, no 2× candidate.

**Phase-2 verdict: NO-GO.** A functioning LLM-driven search over feature combinations cannot
manufacture a positive day-robust edge from the intraday momentum signal; the cross-symbol board
shows the cost wall binds everywhere (and trending pairs are *worse*, killed by spread). The
harness is correct and reusable; the signal is simply sub-cost.

## What remains open (weaker priors; not pursued here)

The day-granularity router is dead, but two narrower angles are not strictly tested:

1. **Coarser horizon** — does a *week's* trendiness predict the next week (vs the intraday
   morning→afternoon test that failed)? Lower frequency may persist better, but also gives far
   fewer trades and still faces the cost wall.
2. **Scheduled-event gating** — the trend edge lived on CPI/FOMC days, which are *known in
   advance* from the economic calendar. But afternoon-only trading on those days was already
   negative here (the move happens at the morning release), so this needs trading the release
   window itself, where spreads blow out (shock regime) — likely self-defeating.

Neither is promising enough to prioritise over the repo's surviving leads
(`project_fx_weekly_meanreversion_lead`).

## Reproduce

```
PY=/path/to/.venv/bin/python   # repo root venv; run from this worktree
$PY -m pytest tests/era_tick -q
$PY -m scripts.era_tick.run_day1 --symbol EURUSD --date 2024-04-10
$PY -m scripts.era_tick.probe_sign_days            # fade vs momentum sign (before cost)
$PY -m scripts.era_tick.exp_confident_momentum     # selectivity + ride, event vs ordinary
$PY -m scripts.era_tick.exp_regime_router          # morning trend signal -> afternoon (OOS)
$PY -m scripts.era_tick.exp_invert_fade            # decompose fade loss; test inversion
$PY -m scripts.era_tick.run_era_tick --symbols EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF  # seed board
$PY -m scripts.era_tick.run_era_tick --symbol EURUSD --budget 40   # full qwen PUCT search
```
