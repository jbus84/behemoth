# BoostLSS Straddle — Review Backlog

Items are grouped by risk. Work highest-risk items first.
Status: `[ ]` open · `[x]` done · `[~]` investigated / no change needed

---

## P0 — Must verify before any live deployment

- [ ] **WFO causality: OOS sigma only at trade time**
  `fit_wfo_gaussian` trains on `y[:-1] = vs[1:]` (next-bar return). Confirm sigma
  predictions used in the candidate loop (`sg_oos[i]`) come from the OOS fold only and
  never from in-sample rows.

- [ ] **`_causal_roll` off-by-one**
  Cumsum indexing at `cs[i - w]` — confirm this correctly excludes bar `i` and there is
  no look-ahead into the current bar.

- [ ] **`oc` sourced from trigger bar, not next bar**
  `oc = log(mid / op) * 1e4` at bar `i`. Confirm `op` is the *open* of bar `i` (first 1m
  mid), not the open of bar `i+1`.

- [ ] **OCO simultaneity: both legs are live simultaneously**
  `simulate_tick_exact` currently scans only for the direction-specific leg. Confirm that
  if the *opposite* leg fills first (price reverses before reaching entry level), the trade
  is correctly labelled `no_fill` rather than silently dropped or miscounted as a fill.

- [ ] **Which script produced the PR #367 cited numbers?**
  `reversion_straddle.py` uses 1m mid fills; `meta_label_straddle.py` uses tick-exact
  bid/ask. Audit the docs/summary to confirm cited figures come from the tick-exact path,
  not the 1m proxy.

---

## P1 — Material cost/P&L impact

- [ ] **TB (time-barrier) exits charged no spread**
  `maker_cost = comm if outcome != "sl"` — TB exits pay commission only. In live, a
  time-exit is a market order (taker). Quantify how many trades are TB and what adding
  spread would do to the headline figure.

- [ ] **Blocked window anchored to bar timestamp, not fill timestamp**
  `blocked_until = t_i + timedelta(hold_hours)` uses bar open time. If fill occurs 30–60
  min into the bar the blackout window is systematically short. Measure the distribution
  of fill lag (entry_idx in tick data) and assess whether this inflates trade count.

- [ ] **Rejected-trade exit spread proxy**
  Option B rejection cost uses `fill_spread` (spread at *entry* tick). The rejection close
  is a separate market order at a different (possibly later) moment. Check whether using
  entry spread is conservative or optimistic for the rejection cost.

- [ ] **Spread validity fallback frequency**
  Lines 445-447: falls back to pair median when `fill_spread <= 0 or > 50`. Log how often
  this fires per pair — high frequency = tick data gaps during exactly the high-volatility
  moments where costs matter most.

---

## P2 — Model integrity

- [ ] **Meta-labeler split by count, not time**
  `fit_meta_label_wfo` uses `n // (N_FOLDS + 1)` count-based splits. If trades cluster
  temporally, train/test may be on structurally different regimes. Compare to a
  time-sorted split and check if AUC changes materially.

- [ ] **No embargo in meta-labeler WFO**
  GaussianLSS WFO has `te_start = tr_end + 8` embargo; meta-labeler has none. With 8h
  hold periods, adjacent trades can share tick data. Add a ~hold_hours embargo and measure
  AUC impact.

- [ ] **TP fill achievability**
  TP is coded as limit at original close — maker, no spread. In a fast-reverting market
  this should be fine, but verify that TP tick `ask_w[j] <= tp_level` (short) /
  `bid_w[j] >= tp_level` (long) actually represents a realistic fill and not a single
  stale tick.

---

## P3 — Edge cases / robustness

- [ ] **Month-boundary concatenation sort order**
  When a trade window spans two months both parquets are concatenated (lines 412-428).
  `pl.concat` does not sort. Confirm both files are individually sorted and concatenation
  preserves temporal order, otherwise tick-exact fill search may find wrong ticks.

- [ ] **`reversion_straddle.py` 1m-proxy cost model**
  `_simulate_one` uses 1m mid for fill price (not bid/ask). Gross distribution will differ
  from tick-exact. Ensure this script is not used for any reported P&L figures; consider
  deprecating or adding a prominent warning.

- [ ] **`_find_direction_1m` used only as post-fill feature**
  Confirm this function is never called on a bar before tick data is loaded, and that
  `direction` only enters the meta-labeler feature set (known at fill time), never used to
  decide whether to place the OCO straddle.

---

## Ideas / future improvements (not blocking)

- [ ] Dynamic hold_hours: exit earlier if sigma decays — currently hard-capped at 8h
- [ ] Per-pair meta-threshold tuning with proper multiplicity correction
- [ ] Live retraining cadence: monthly rolling vs. expanding window
- [ ] Broker API integration (Pepperstone cTrader) — execution architecture design
- [ ] Stress-test: 2020 COVID vol spike, 2022 EURUSD trend — check max drawdown under realistic position sizing
