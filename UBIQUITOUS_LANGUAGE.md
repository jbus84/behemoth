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
| **Warmup** | The historical feature replay used to seed live inference state before current predictions begin. | Backfill, preload, phase warmup |
| **Bar Alignment Ticks** | The tick-count modulus used when sizing **Warmup** loads so the runtime's open-bar accumulator at start matches what governance had at the same moment. Equals the largest candidate `bar_ticks` in the active universe. | Phase bar ticks, alignment window |
| **Reconciliation** | The process of matching broker state, local state, and promoted runtime state after restart or drift. | Resync, state repair |
| **Trade Tracking State** | The persisted local record of live orders, barriers, and lifecycle progress. | Local cache, live DB |
| **Runtime State** | The in-process and persisted state used by the Live Runtime to hold Tick Bars, Feature Set readiness, trades, and account risk reservations. | DB, cache, state manager |
| **State Query View** | A read-only view of Runtime State used by business logic that must not depend on table layout or persistence details. | Raw DB access, direct SQL, state helper |

## Runtime candidate resolution

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Candidate Catalog** | The runtime source of Candidate State definitions, model bindings, and production caps across live and historical modes. | Registry switch, candidate registry, historical registry |
| **Runtime Candidate Contract** | The resolved Candidate State, model artifact binding, cap, cache key, and source month used for one prediction cycle. | Runtime contract, model contract, candidate bundle |
| **Model Binding** | The locked model and threshold artifact paths and hashes required to score a Candidate State. | Model config, model path, artifact binding |
| **Production Cap** | The governed maximum execution cap in pips applied to runtime scoring for a symbol. | Cap, live cap, production limit |
| **Cache Key** | The symbol or symbol-month identifier used to bind runtime model, threshold, and historical prediction caches. | Model key, registry key |

## Runtime Feature Set contract

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Feature Schema** | The versioned manifest that names the Feature Set, rolling windows, lag rules, and feature definitions. | Feature list, columns tuple |
| **Feature Definition** | A single governed feature name with its computation group and source dependencies. | Feature metadata, feature row |
| **Model Feature Contract** | The enforceable runtime contract that pins Feature Schema version, Feature Set order, and Warmup bar count. | Feature check, model schema |
| **Feature Computation** | The causal transformation from Tick Bars into the Feature Set used by the Stage-3 model. | Feature engineering, dataframe logic |

## Barrier and order lifecycle

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Barrier Scan** | A pending runtime watch created from a selected Candidate State that waits for an upper or lower barrier touch. | Pending signal, scan row, setup |
| **Barrier Evaluation** | The completed-bar decision step that advances Barrier Scans and emits Barrier Actions. | Barrier check, scan update |
| **Barrier Action** | A runtime instruction emitted by Barrier Evaluation to open, close, or release a reservation. | Action dict, order signal, event |
| **Barrier State Mutation** | The explicit state transition made to a Barrier Scan during Barrier Evaluation. | Side effect, SQL update |
| **Order Lifecycle** | The Java-side progression from order submission through fill, Python sync, close, and final trade update. | Order flow, trade lifecycle |
| **Order Lifecycle Event** | A broker or local execution event that advances the Order Lifecycle. | Order callback, order message |
| **Worker Queue** | The per-symbol in-memory queue that buffers ticks before Tick Batch submission to Python. | Tick queue, pending queue |
| **Tick Batch** | A per-symbol group of ticks submitted from JForex to the Python runtime for ingestion and bar completion. | Batch, tick payload |
| **Python API Contract** | The set of Python runtime endpoints, payloads, response shapes, and timeout profiles consumed by JForex. | Bridge protocol, HTTP API |

## Account risk lifecycle

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Account Risk Decision** | The current account-level decision that allows or blocks new trading based on account snapshots and governed limits. | Risk eval, risk check, gate result |
| **Trade Guard Decision** | The per-candidate decision that allows or blocks a selected Candidate State based on cost, edge, and reservation capacity. | Trade risk, cost gate |
| **Reservation** | A runtime account-risk allocation held for a selected Candidate State until the order opens, closes, expires, or is released. | Risk hold, allocation, pending risk |
| **Reservation Lifecycle** | The allowed progression of a Reservation through pending, open, closed, released, or expired states. | Reservation state machine, risk lifecycle |
| **Entry Gate** | The combined runtime decision that determines whether a selected Candidate State may become a Barrier Scan or broker order. | Entry check, allow trading flag |

## Historical replay

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Historical Mode** | The runtime mode that scores by symbol-month Governance Locks and locked historical prediction artifacts. | Backtest mode, historical auto |
| **Historical Prediction Artifact** | The locked prediction parquet used to replay the governed prediction universe for a symbol-month. | Prediction file, historical predictions |
| **Historical Prediction Load Status** | The explicit result of attempting to load a Historical Prediction Artifact. | Empty predictions, cache status |
| **Missing Historical Prediction Artifact** | A load status that means the locked historical prediction parquet was not found. | No predictions, empty universe |

## Thresholds and execution

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Rolling Threshold** | The current deployment threshold derived from recent governed prediction behavior. | Dynamic cutoff, warm threshold |
| **Threshold Drift** | A live deviation between expected rolling-threshold behavior and observed runtime behavior. | Threshold bug, flat threshold |
| **Execution Adapter** | The broker-facing layer that turns Python governance decisions into JForex actions. | Bridge, broker shim |

## Parity tolerance

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Runtime Variance** | An expected live-versus-governance difference that remains inside the governed runtime contract. | Flexibility, mismatch |
| **Tolerance Band** | The explicit allowed range of live-versus-governance difference for a given metric or behavior. | Wiggle room, soft tolerance |
| **Material Drift** | A live-versus-governance difference large enough to call certification compatibility into doubt. | Big mismatch, serious variance |
| **Parity Breach** | A confirmed live behavior difference that falls outside the governed runtime contract and requires investigation or blocking action. | Failure, broken parity |
| **Governance Selected Signal Count** | The count of selected signal rows from the month-scoped Governance Lock predictions in the evaluated window. | locked selected count, locked_sel |
| **Independent Label P&L** | The sum of per-row label outcomes evaluated independently for each selected governance signal. | locked pips, expected pips, governance pips |
| **Runtime Trade Count** | The count of trades actually opened by the stateful runtime lifecycle. | JForex trades, broker count |
| **Runtime Realized P&L** | The realized pip result from closed runtime trades. | broker pips, JForex P&L |
| **Stateful Lifecycle Expected P&L** | The expected pip result from replaying governance signals through the same scan, touch, open, hold, and close constraints as the runtime. | label pips, locked pips, target pips |

## Relationships

- A **Certification Run** produces **Evidence Root** contents and a final verdict of **PASS** or **FAIL**.
- **Monthly Recert** is the official **Certification Run** used to justify **Promotion** for a **Deployment Period**.
- **Governance Runtime** is the offline counterpart to **Live Runtime** and contains staged research, certification, and promotion-gating workflows.
- **Stage 12**, **Stage 13**, and **Stage 14** are certification surfaces within the overall staged governance process.
- **Raw Tick Data** is transformed into **Tick Bars**, which are transformed into the **Velocity Dataset**.
- **Opportunity Mining** creates a broad **Candidate Universe** of **Candidate State** definitions from the **Velocity Dataset**.
- **Monthly WFO** performs **Model Fit** and **Threshold Fit** to score the next **Test Month** under strict causal ordering.
- **Reduced-Core Rolling** converts scored candidates into a monthly **Shortlist** of **Allowed State** entries.
- **Stop-Limit Realism**, **Tick-Exact Verification**, and the **Robustness Filter** harden the shortlist before governance promotion decisions are made.
- **Independent Label P&L** is not **Stateful Lifecycle Expected P&L** and must not be used as a direct parity target for **Runtime Realized P&L**.
- **Governance Selected Signal Count** is a signal-layer measure; **Runtime Trade Count** is a lifecycle-layer measure.
- A **Promotion** is valid only when a **PASS** run has matching **Provenance** and a matching **Promoted Lock Set**.
- A **Promoted Lock Set** determines **Symbol Universe** membership, **Deployment Period**, and each symbol's **GO** or **NO_GO** state.
- A symbol may be **NO_GO** without the **Certification Run** being a **FAIL**.
- **Restart Eligibility** evaluates whether the **Live Runtime** may resume using existing **Trade Tracking State**.
- `RESTART_ELIGIBLE_DRAIN_ONLY` is a valid restart outcome when **Reconciliation** succeeds for monitoring but not for new entries.
- **Warmup** must complete before stable **Rolling Threshold** behavior can be trusted.
- The **Execution Adapter** applies governed decisions in broker space.
- A **Candidate Catalog** resolves a **Runtime Candidate Contract** before the Live Runtime computes the **Feature Set**.
- A **Runtime Candidate Contract** contains Candidate States, a **Model Binding**, a **Production Cap**, and a **Cache Key**.
- A **Feature Schema** defines the **Feature Set**, and the **Model Feature Contract** enforces its order and Warmup requirements.
- **Feature Computation** consumes **Tick Bars** and emits the **Feature Set** for a **Candidate State**.
- A selected **Candidate State** may create a **Reservation** and a **Barrier Scan** only after the **Entry Gate** allows it.
- **Barrier Evaluation** consumes a **State Query View** of the latest Tick Bar and produces **Barrier Actions** plus **Barrier State Mutations**.
- An `OPEN_MARKET` **Barrier Action** enters the Java **Order Lifecycle** through the **Execution Adapter**.
- The **Worker Queue** forms a **Tick Batch**, and a Tick Batch may complete one or more Tick Bars.
- In **Historical Mode**, the **Historical Prediction Artifact** constrains which Candidate States are eligible for replay at a given timestamp.
- **Missing Historical Prediction Artifact** is a load failure state, not proof that there were no selected predictions.
- **Account Risk Decision**, **Trade Guard Decision**, and **Reservation Lifecycle** are separate decisions and must not be collapsed into a single boolean.

## Parity principle

- The **Governance Runtime** should produce artifacts, verdicts, and certification evidence that are semantically aligned with the **Live Runtime**.
- The target is **semantic parity**, not exact trade-by-trade equality.
- Exact live outcomes may differ because of broker timing, spread, fill conditions, callback ordering, account state, and restart or reconciliation context.
- Expected live differences that stay inside an explicit **Tolerance Band** are **Runtime Variance**, not failure.
- A valid certification process is one that would catch material drift between **Governance Runtime** behavior and **Live Runtime** behavior before **Promotion**.
- **Material Drift** means the variance is large enough that certification compatibility is in doubt.
- A **Parity Breach** means the live behavior is outside the governed contract and requires investigation or blocking action.

## Supporting concepts

These phrases appear in supporting docs and implementation discussion, but they are not part of the tight canonical vocabulary above:

- "final verdict" for the overall `PASS`/`FAIL` outcome of a certification run
- "promotion bundle" or "artifact bundle" for the monthly collection of governed outputs reviewed before Promotion
- "trade lifecycle" or "OCO flow" for the sequence from setup through execution management
- "model traffic" or "signals" for the stream of live predictions after Warmup
- "contract" should be qualified as **Runtime Candidate Contract**, **Model Feature Contract**, or **Python API Contract**
- "state" should be qualified as **Runtime State**, **Trade Tracking State**, **Barrier Scan**, or **Reservation**
- "action" should be qualified as **Barrier Action**, **Order Lifecycle Event**, or operator action

## Example dialogue

> **Dev:** "If AUDUSD is quarantined for this Deployment Period, does that mean Monthly Recert failed?"
>
> **Domain expert:** "No. **Monthly Recert** can still be a **PASS** while AUDUSD is **NO_GO** inside the **Promoted Lock Set**."
>
> **Dev:** "When the Live Runtime receives a selected Candidate State, can it submit an order immediately?"
>
> **Domain expert:** "No. The **Candidate Catalog** first resolves a **Runtime Candidate Contract**, then the **Entry Gate** applies the **Account Risk Decision** and **Trade Guard Decision** before a **Barrier Scan** can be registered."
>
> **Dev:** "And the order happens when the Barrier Scan touches?"
>
> **Domain expert:** "Yes. **Barrier Evaluation** turns a touch into a **Barrier Action** and records a **Barrier State Mutation**. The **Execution Adapter** then starts the Java **Order Lifecycle**."
>
> **Dev:** "In Historical Mode, if the prediction parquet is missing, should I treat that as no selected predictions?"
>
> **Domain expert:** "No. That is a **Missing Historical Prediction Artifact** load status, not an empty prediction universe."
>
> **Dev:** "Can I compare **Independent Label P&L** directly with **Runtime Realized P&L**?"
>
> **Domain expert:** "No. **Independent Label P&L** scores each selected signal independently. Runtime P&L parity needs **Stateful Lifecycle Expected P&L** because the runtime applies scan, touch, open, hold, and close constraints."
>
> **Dev:** "So if live doesn’t line up perfectly with governance, is that automatically a problem?"
>
> **Domain expert:** "No. If the difference stays inside the approved **Tolerance Band**, it is **Runtime Variance**. It becomes **Material Drift** or a **Parity Breach** only when it falls outside the governed contract."

## Flagged ambiguities

- "fail" has been used for both process invalidity and symbol exclusion. Use **FAIL** only for process/evidence invalidity, and **NO_GO** for symbol non-deployment.
- "month" has been used to mean both a governed deployment period and the process result for that period. Prefer **Deployment Period** for the governed time scope and **Monthly Recert** or **Certification Run** for the process.
- "promotion" has sometimes meant both selecting artifacts and starting live. Use **Promotion** for approving the lock/artifact set, and **Live Runtime** for actually running production.
- "warmup" and "backfill" have been used interchangeably. Prefer **Warmup** for the inference-state replay that seeds live behavior.
- "live" has been used to mean code branch, runtime process, and broker state. Use **Live Runtime** for the running process and **Promoted Lock Set** for the approved deployment content.
- Legacy restart labels such as `clean_resumable`, `reconcilable`, and `incompatible` conflict with the approved operator-facing vocabulary. Prefer `RESTART_ELIGIBLE`, `RESTART_ELIGIBLE_DRAIN_ONLY`, and `RESTART_BLOCKED`.
- "training" has been used too broadly for mining, fitting, selection, and certification. Use **Opportunity Mining** for Stage 2 hypothesis generation, **Model Fit** and **Threshold Fit** for Stage 3 fitting, **Reduced-Core Rolling** for Stage 5 state selection, and **Certification Run** for Stage 12-14 validation.
- "candidate", "shortlist", and "allowed state" have been used interchangeably. Keep them ordered: **Candidate State** before selection, **Shortlist** after reduced-core selection, **Allowed State** once written into governance artifacts.
- "bundle", "evidence", and "lock" have been blurred together. Prefer **Certification Evidence** for the reports proving a run, and **Governance Lock** or **Promoted Lock Set** for deployment manifests.
- "flexibility" is too vague for live-vs-governance differences. Use **Runtime Variance** for acceptable in-contract differences, **Material Drift** for concerning divergence, and **Parity Breach** for out-of-contract behavior.
- "locked pips" and "locked selected" obscure the semantic layer being measured. Use **Independent Label P&L** for per-row label outcomes and **Governance Selected Signal Count** for selected signal counts.
- "contract" is now overloaded after the refactor. Use **Runtime Candidate Contract** for candidate/model/cap resolution, **Model Feature Contract** for Feature Set schema enforcement, and **Python API Contract** for Java-to-Python endpoint semantics.
- "registry" is ambiguous between live and historical candidate sources. Use **Candidate Catalog** for runtime resolution across modes.
- "action" is ambiguous between broker commands, barrier outputs, and operator work. Use **Barrier Action** for runtime lifecycle outputs and **Order Lifecycle Event** for broker/order callbacks.
- "state" is too broad for runtime discussions. Use **Runtime State** for the stored runtime surface, **Trade Tracking State** for persisted broker lifecycle records, **Barrier Scan** for OCO scan rows, and **Reservation** for account-risk allocations.
- "empty predictions" must not be used for missing files in Historical Mode. Use **Missing Historical Prediction Artifact** when the locked artifact cannot be loaded.
- "risk gate" has blurred account-level and trade-level decisions. Use **Account Risk Decision** for account limits and **Trade Guard Decision** for per-candidate checks.
