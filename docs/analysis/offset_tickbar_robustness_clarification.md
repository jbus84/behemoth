# Offset Tick-Bar Robustness Clarification

Date: `2026-03-13`

## Purpose

Clarify the difference between the earlier adaptive offset reports and the later frozen-month offset screen so EURUSD and GBPUSD are not described inconsistently.

## What The Earlier "Stable" Reports Mean

The older symbol reports:

- `docs/analysis/eurusd_offset_tickbar_robustness_report.md`
- `docs/analysis/gbpusd_offset_tickbar_robustness_report.md`

show:

- `study_mode: adaptive`
- `offsets_evaluated: 1`
- `offsets_screened: 1`
- `offsets_refined: 0`

Those reports only evaluated `offset 0`. Their `stable` classification means the baseline repo pipeline was internally consistent at `offset 0`. They do **not** demonstrate robustness across non-zero offsets.

## What The Frozen-Month Screen Means

The frozen-month screen under:

- `data/analysis/tick_opportunity_mining/offset_robustness_frozen/`

holds the model and reduced-core schedule fixed, then evaluates explicit offsets:

- `0,10,20,30,40,50,60,70,80,90`

For EURUSD and GBPUSD the frozen screen shows:

- `offset 0` is `ok`
- non-zero offsets are `degraded`

The degradation is driven by event-selection instability, not by immediate profitability collapse:

- EURUSD: non-zero selected-event overlap is about `0.29-0.31`
- GBPUSD: non-zero selected-event overlap is about `0.39`
- GBPUSD also remains below the `0.90` canonical state coverage threshold at about `0.884615`

## Correct Interpretation

The precise statement is:

- EURUSD and GBPUSD were previously shown to be **baseline-consistent at offset 0**
- EURUSD and GBPUSD have **not** been shown to be robust to non-zero tick/bar offsets
- the frozen-month screen is the first local artifact on disk that demonstrates the non-zero offset sensitivity directly

## Practical Guidance

When summarizing offset results:

- use "baseline ok" for the earlier adaptive `offset 0` reports
- use "not offset-robust under frozen-month screening" for the newer frozen outputs

Do not collapse those two claims into "EURUSD and GBPUSD were fine" without specifying whether "fine" means baseline parity or true non-zero offset robustness.
