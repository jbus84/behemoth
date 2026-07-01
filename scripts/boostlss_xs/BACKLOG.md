# BoostLSS Straddle — Review Backlog

Items are grouped by risk. Work highest-risk items first.
Status: `[ ]` open · `[x]` done · `[~]` investigated / no change needed

---

## P0 — Must verify before any live deployment

- [x] **WFO causality: OOS sigma only at trade time**
  `sg_oos` initialised to `nan`; candidate loop skips `nan` rows; only OOS fold
  windows are ever written. Clean.

- [x] **`_causal_roll` off-by-one**
  Window at position `i` uses `cs[i] - cs[i-w]` = bars `[i-w+1 … i]`. Current bar
  included (known at bar close). Not look-ahead. Clean.

- [x] **`oc` sourced from trigger bar, not next bar**
  `op = .first()` over 1h bucket = first 1m mid of bar `i`. `mid = .last()`. Both from
  bar `i`, known at close. Clean.

- [x] **OCO simultaneity: both legs are live simultaneously** ← **FIXED**
  Old code pre-assigned direction from 1m mid (`_find_direction_1m`) and only scanned
  for that one leg. Rewritten: `simulate_tick_exact` now scans all ticks for whichever
  of `BID >= upper_entry` / `ASK <= lower_entry` fires first. Both-same-tick case
  returns `no_fill`. `_find_direction_1m` → `_has_fill_1m` (pre-filter only, no
  direction). P1 blocked-window fix bundled: `blocked_until_tick` now anchored to actual
  fill tick timestamp, not bar open.

- [~] **Which script produced the PR #367 cited numbers?**
  `reversion_straddle.py` docstring says "Pending tick-exact verification" and uses 1m
  mid + fixed TP/SL bps. PR #367 headline (+3.65 bps, 93.3% win) matches that script.
  Tick-exact numbers (lower gross, honest cost) are from `meta_label_straddle.py` and
  subsequent PRs. No code fix needed; docs should note this distinction.

---

## P1 — Material cost/P&L impact

- [x] **TB (time-barrier) exits charged no spread** ← **FIXED**
  `maker_cost` condition changed from `outcome != "sl"` to `outcome == "tp"` in both
  `meta_label_straddle.py` and `reversion_straddle.py`. TB exits now pay `comm + spread`
  (market order at expiry). Estimated drag: −0.05 to −0.16 bps/fill depending on TB%
  (5–15% of fills). Headline likely moves from +1.019 → ~+0.91 to +0.97 bps/fill.
  Exact figure needs a full re-run.

- [x] **Blocked window anchored to bar timestamp, not fill timestamp** ← **FIXED**
  `blocked_until_tick` now set from actual tick fill timestamp (`fill_ts + hold_hours`).
  Bundled with OCO simultaneity fix above.

- [~] **Rejected-trade exit spread proxy**
  Rejected trades are momentum bars (large `|oc|`). Entry fill and rejection close both
  occur during the same momentum spike, so `fill_spread` is a reasonable proxy for the
  close spread — likely slightly conservative (wide momentum spread) rather than optimistic.
  No systematic bias toward flattering P&L. No fix needed.

- [ ] **Spread validity fallback frequency**
  Lines 445-447: falls back to pair median when `fill_spread <= 0 or > 50`. Log how often
  this fires per pair — high frequency = tick data gaps during exactly the high-volatility
  moments where costs matter most.

---

## P2 — Model integrity

- [~] **Meta-labeler split by count, not time**
  Per-pair trades are already in time order, so count-based split = time-based split
  within a pair. Count clustering across years is actually desirable (trains on
  high-vol regimes, tests on what follows). No fix needed.

- [~] **No embargo in meta-labeler WFO**
  Non-overlap blackout guarantees adjacent trades are ≥ 8h apart. Nearest training trade
  is ≥ 8h before any test trade. Key feature `oc` (trigger bar open-to-close) has near-zero
  autocorrelation at 8h lag. Shared `mom_1/4/24` lookback windows are slow-moving and not
  sharp predictors. Contamination risk is negligible. No fix needed.

- [~] **TP fill achievability**
  TP level = `entry_k × sigma` of reversion (e.g. 5 bps for sigma=10 entry_k=0.5) —
  physically reachable, not extreme. Fill rule uses ask (short close) / bid (long close):
  correct side for limit exit. Stale-tick misfire would produce an outlier gross visible
  in the distribution. Dukascopy feed quality makes crossed ticks rare. Clean.

---

## P3 — Edge cases / robustness

- [~] **Month-boundary concatenation sort order**
  `_load_month_pair` calls `.sort("timestamp")` after `pl.concat` so each individual
  month tuple is sorted. Cross-month concat is `np.concatenate([m1, m2])` — since all
  of m1 (month-end) precedes all of m2 (month-start) by calendar, the result is
  chronologically ordered by construction. Clean.

- [x] **`reversion_straddle.py` 1m-proxy cost model**
  Added DEPRECATED warning to docstring. Authoritative numbers come from
  `meta_label_straddle.py` only.

- [x] **`_find_direction_1m` used only as post-fill feature**
  Function renamed `_has_fill_1m` and no longer returns direction at all (P0 fix).
  Direction is discovered exclusively from tick bid/ask in `simulate_tick_exact`.

---

## Ideas / future improvements (not blocking)

- [ ] Dynamic hold_hours: exit earlier if sigma decays — currently hard-capped at 8h
- [ ] Per-pair meta-threshold tuning with proper multiplicity correction
- [ ] Live retraining cadence: monthly rolling vs. expanding window
- [ ] Broker API integration (Pepperstone cTrader) — execution architecture design
- [ ] Stress-test: 2020 COVID vol spike, 2022 EURUSD trend — check max drawdown under realistic position sizing
