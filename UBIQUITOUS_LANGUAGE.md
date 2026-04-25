# Ubiquitous Language

## Governance lifecycle

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Certification Run** | A bounded execution of the staged governance process that produces evidence and verdicts for a target runtime context. | Cert, stage run, monthly run |
| **Monthly Recert** | The official certification run for the current deployment period that gates promotion to live. | Recert month, monthly pass |
| **Promotion** | The act of approving a certified lock set and artifact set for live use. | Deploy, publish, point live |
| **Promoted Lock Set** | The authoritative lock bundle that defines the artifact, symbol, and month decisions live must use. | Live lock, promoted system, runtime config |
| **Provenance** | The recorded branch, commit, inputs, and artifact lineage that explain why a certification result is valid. | Metadata, context |
| **Evidence Root** | The filesystem location containing the reports and artifacts a certification run relied on. | Output dir, report folder |
| **Freshness Gate** | A check that rejects stale or mismatched evidence before promotion or restart. | Recency check, staleness check |
| **Deployment Period** | The governed model month or trading period the promoted artifacts apply to. | Month, runtime month |

## Certification surfaces

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Stage 12** | The API parity certification surface that checks Python runtime behavior against expected predictions. | API smoke, pre-stage |
| **Stage 13** | The Dukascopy/TestClient certification surface that validates governed runtime behavior before JForex runtime certification. | Dukascopy cert, TestClient cert |
| **Stage 14** | The JForex runtime certification surface that validates runtime parity and operational readiness. | JForex cert, runtime cert |
| **Process Verdict** | The final `PASS` or `FAIL` outcome of a certification surface or aggregated certification run. | Status, green/red |
| **Symbol Decision** | The final `GO` or `NO_GO` deployment decision for an individual symbol. | Deployable flag, symbol status |

## Data construction

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Raw Tick Data** | The canonical timestamped bid/ask tick stream used as the source material for all downstream bars and replay. | Raw data, history |
| **Tick Bars** | Bars formed by a fixed number of ticks rather than fixed clock time. | Candles, time bars |
| **Velocity Dataset** | The tick-bar feature dataset used as the canonical Stage-2 and Stage-3 input surface. | Training data, model data |
| **Feature Set** | The governed predictor columns derived causally from the velocity dataset for scoring candidate events. | Inputs, signals |
| **Label Set** | The forward-looking target fields derived under causal rules for mining and model evaluation. | Outcomes, targets |

## Research and fitting

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Opportunity Mining** | Stage 2 hypothesis generation that scans the velocity dataset for broad, train-only positive-expectancy candidate states. | Training, fitting, selection |
| **Candidate State** | A mined OCO or directional regime definition parameterized by structure such as `bar_ticks`, `horizon`, and `barrier_pips`. | Setup, signal |
| **Candidate Universe** | The set of candidate states admitted to later evaluation after train-only mining filters. | Final shortlist, production states |
| **Monthly WFO** | Stage 3 rolling month-by-month fitting and scoring where prior months train the next test month. | Backtest, monthly training |
| **Model Fit** | The act of fitting the Stage-3 classifier on the allowed rolling training window. | Training run, model selection |
| **Threshold Fit** | The causal derivation of the execution threshold from train-only or rolling-history probability distributions. | Cutoff tuning, signal filter |
| **Test Month** | The month being scored by a fit that used only prior months. | Live month, current month |
| **Model Validity** | The rule that a Stage-3 fit is valid only for the specific scored test month. | Long-lived model, reusable fit |

## Selection and hardening

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Reduced-Core Rolling** | Stage 5 leakage-safe month-by-month state selection using only prior train months for each deployed month. | Post-hoc filtering, reduced core |
| **Shortlist** | The provisional set of candidate states that survive reduced-core selection for a specific month. | Final lock set, GO set |
| **Allowed State** | A shortlisted state that is explicitly written into the governed deployable state list for runtime use. | Candidate state, any state |
| **Stop-Limit Realism** | Stage 4 execution-hardening analysis that applies overshoot, fill, and no-touch semantics to selected opportunities. | Execution backtest, slippage check |
| **Tick-Exact Verification** | Stage 6 causal replay that re-evaluates shortlisted states against canonical tick data at exact execution granularity. | Sanity check, spot check |
| **Robustness Filter** | Stage 8 stress and stability evaluation that rejects states or symbols that do not survive perturbation and month-stability checks. | Certification, final pass |
| **Execution Quantile** | The governed quantile used to select the executable tail of predicted opportunities. | Threshold, confidence |

## Governance artifacts

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Candidate Build** | The monthly artifact bundle produced before promotion, containing lock inputs and governed outputs for a deployment period. | Promotion bundle, history dir |
| **Certification Evidence** | The reports, summaries, and machine-readable status files that justify a process verdict. | Logs, outputs |
| **Governance Lock** | The symbol-specific manifest that binds allowed states, model artifacts, and runtime assumptions for deployment. | Config file, model file |

## Deployment decisions

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **PASS** | The process completed correctly and produced valid evidence. | Green month, deployable |
| **FAIL** | The process or evidence is invalid and cannot justify promotion. | No-go, quarantined |
| **GO** | A symbol is eligible for deployment under a valid promoted lock set. | Passed, active |
| **NO_GO** | A symbol is intentionally not deployed even though the governing process did not fail. | Failed symbol, bad month |
| **Quarantine** | A temporary symbol-level exclusion from deployment for a specific governed period. | Failure, ban |
| **Symbol Universe** | The set of symbols under active governance consideration for a run. | Active pairs, trading pairs |

## Runtime operation

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Authoritative Runtime** | The designated local runtime context whose code, artifacts, and credentials are trusted for official certification or live operation. | Any worktree, convenient checkout |
| **Governance Runtime** | The authoritative offline execution context that runs staged research, certification, and promotion-gating workflows against governed artifacts. | Offline process, pipeline |
| **Live Runtime** | The production trading process that must run only from authoritative `main` with the promoted lock set. | Live system, production bot |
| **Restart Eligibility** | The preflight verdict that decides whether live may safely resume from preserved state after interruption. | Restart check, crash recovery |
| **RESTART_ELIGIBLE** | The restart result that allows preserved-state live resumption with normal entry behavior. | Clean resumable, normal restart |
| **RESTART_ELIGIBLE_DRAIN_ONLY** | The restart result that allows reconciliation and exposure management but blocks new entries. | Drain only, reconcilable |
| **RESTART_BLOCKED** | The restart result that forbids live startup until state, artifacts, or broker context are proven safe. | Incompatible, blocked restart |
| **Warmup** | The historical feature replay used to seed live inference state before current predictions begin. | Backfill, preload |
| **Reconciliation** | The process of matching broker state, local state, and promoted runtime state after restart or drift. | Resync, state repair |
| **Trade Tracking State** | The persisted local record of live orders, barriers, and lifecycle progress. | Local cache, live DB |

## Thresholds and execution

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Rolling Threshold** | The current deployment threshold derived from recent governed prediction behavior. | Dynamic cutoff, warm threshold |
| **Threshold Drift** | A live deviation between expected rolling-threshold behavior and observed runtime behavior. | Threshold bug, flat threshold |
| **Barrier Lifecycle** | The governed progression from predicted setup to order placement, management, and closure. | Trade lifecycle, OCO flow |
| **Prediction Activity** | The stream of live inference outputs produced after warmup and before execution decisions. | Signals, model traffic |
| **Execution Adapter** | The broker-facing layer that turns Python governance decisions into JForex actions. | Bridge, broker shim |

## Parity tolerance

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Runtime Variance** | An expected live-versus-governance difference that remains inside the governed runtime contract. | Flexibility, mismatch |
| **Tolerance Band** | The explicit allowed range of live-versus-governance difference for a given metric or behavior. | Wiggle room, soft tolerance |
| **Material Drift** | A live-versus-governance difference large enough to call certification compatibility into doubt. | Big mismatch, serious variance |
| **Parity Breach** | A confirmed live behavior difference that falls outside the governed runtime contract and requires investigation or blocking action. | Failure, broken parity |

## Relationships

- A **Certification Run** produces **Evidence Root** contents and a process verdict of **PASS** or **FAIL**.
- **Monthly Recert** is the official **Certification Run** used to justify **Promotion** for a **Deployment Period**.
- **Governance Runtime** is the offline counterpart to **Live Runtime** and contains staged research, certification, and promotion-gating workflows.
- **Stage 12**, **Stage 13**, and **Stage 14** are certification surfaces within the overall staged governance process.
- **Raw Tick Data** is transformed into **Tick Bars**, which are transformed into the **Velocity Dataset**.
- **Opportunity Mining** creates a broad **Candidate Universe** of **Candidate State** definitions from the **Velocity Dataset**.
- **Monthly WFO** performs **Model Fit** and **Threshold Fit** to score the next **Test Month** under strict causal ordering.
- **Reduced-Core Rolling** converts scored candidates into a monthly **Shortlist** of **Allowed State** entries.
- **Stop-Limit Realism**, **Tick-Exact Verification**, and the **Robustness Filter** harden the shortlist before governance promotion decisions are made.
- A **Candidate Build** packages the governed outputs for a **Deployment Period** before certification and promotion.
- A **Promotion** is valid only when a **PASS** run has matching **Provenance** and a matching **Promoted Lock Set**.
- A **Promoted Lock Set** determines **Symbol Universe** membership, **Deployment Period**, and each symbol's **GO** or **NO_GO** state.
- A symbol may be **NO_GO** without the **Certification Run** being a **FAIL**.
- **Restart Eligibility** evaluates whether the **Live Runtime** may resume using existing **Trade Tracking State**.
- `RESTART_ELIGIBLE_DRAIN_ONLY` is a valid restart outcome when **Reconciliation** succeeds for monitoring but not for new entries.
- **Warmup** must complete before stable **Prediction Activity** and **Rolling Threshold** behavior can be trusted.
- The **Execution Adapter** consumes governed decisions from the **Barrier Lifecycle** and applies them in broker space.

## Parity principle

- The **Governance Runtime** should produce artifacts, verdicts, and certification evidence that are semantically aligned with the **Live Runtime**.
- The target is **semantic parity**, not exact trade-by-trade equality.
- Exact live outcomes may differ because of broker timing, spread, fill conditions, callback ordering, account state, and restart or reconciliation context.
- Expected live differences that stay inside an explicit **Tolerance Band** are **Runtime Variance**, not failure.
- A valid certification process is one that would catch material drift between **Governance Runtime** behavior and **Live Runtime** behavior before **Promotion**.
- **Material Drift** means the variance is large enough that certification compatibility is in doubt.
- A **Parity Breach** means the live behavior is outside the governed contract and requires investigation or blocking action.

## Example dialogue

> **Dev:** "If AUDUSD is quarantined for this deployment period, does that mean Monthly Recert failed?"
>
> **Domain expert:** "No. **Monthly Recert** can still be a **PASS** while AUDUSD is **NO_GO** inside the **Promoted Lock Set**."
>
> **Dev:** "So a restart after a crash should still bring live up?"
>
> **Domain expert:** "Only if **Restart Eligibility** passes. If state reconciles but new entries are unsafe, live comes up as `RESTART_ELIGIBLE_DRAIN_ONLY`."
>
> **Dev:** "What is the common name for the offline side of this system?"
>
> **Domain expert:** "Use **Governance Runtime**. It is the authoritative offline process that produces the evidence and artifacts the **Live Runtime** is allowed to use."
>
> **Dev:** "If live doesn’t line up perfectly with governance, is that automatically a problem?"
>
> **Domain expert:** "No. If the difference stays inside the approved **Tolerance Band**, it is **Runtime Variance**. It becomes **Material Drift** or a **Parity Breach** only when it falls outside the governed contract."
>
> **Dev:** "Where does training stop and certification begin?"
>
> **Domain expert:** "**Opportunity Mining** and **Monthly WFO** are research and fitting. **Reduced-Core Rolling** and **Stop-Limit Realism** are selection hardening. **Stage 12-14** are certification surfaces, not training."
>
> **Dev:** "And promotion should only happen when the provenance matches the exact certified commit?"
>
> **Domain expert:** "Exactly. **Promotion** depends on exact **Provenance** in the **Authoritative Runtime**, not just being on `main`."

## Flagged ambiguities

- "fail" has been used for both process invalidity and symbol exclusion. Use **FAIL** only for process/evidence invalidity, and **NO_GO** for symbol non-deployment.
- "month" has been used to mean both a governed deployment period and the process result for that period. Prefer **Deployment Period** for the governed time scope and **Monthly Recert** or **Certification Run** for the process.
- "promotion" has sometimes meant both selecting artifacts and starting live. Use **Promotion** for approving the lock/artifact set, and **Live Runtime** for actually running production.
- "warmup" and "backfill" have been used interchangeably. Prefer **Warmup** for the inference-state replay that seeds live behavior.
- "live" has been used to mean code branch, runtime process, and broker state. Use **Live Runtime** for the running process and **Promoted Lock Set** for the approved deployment content.
- Legacy restart labels such as `clean_resumable`, `reconcilable`, and `incompatible` conflict with the approved operator-facing vocabulary. Prefer `RESTART_ELIGIBLE`, `RESTART_ELIGIBLE_DRAIN_ONLY`, and `RESTART_BLOCKED`.
- "training" has been used too broadly for mining, fitting, selection, and certification. Use **Opportunity Mining** for Stage 2 hypothesis generation, **Model Fit** and **Threshold Fit** for Stage 3 fitting, **Reduced-Core Rolling** for Stage 5 state selection, and **Certification Run** for Stage 12-14 validation.
- "candidate", "shortlist", and "allowed state" have been used interchangeably. Keep them ordered: **Candidate State** before selection, **Shortlist** after reduced-core selection, **Allowed State** once written into governance artifacts.
- "bundle", "evidence", and "lock" have been blurred together. Use **Candidate Build** for the monthly artifact bundle, **Certification Evidence** for the reports proving the run, and **Governance Lock** or **Promoted Lock Set** for deployment manifests.
- "flexibility" is too vague for live-vs-governance differences. Use **Runtime Variance** for acceptable in-contract differences, **Material Drift** for concerning divergence, and **Parity Breach** for out-of-contract behavior.
