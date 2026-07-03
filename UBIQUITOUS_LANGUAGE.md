# Ubiquitous Language

Canonical vocabulary for this repo. Use only the terms below; avoid the aliases listed.

## Deployment decisions

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **PASS** | The process completed correctly and produced valid evidence. | Green, deployable |
| **FAIL** | The process or evidence is invalid. | No-go, quarantined |
| **GO** | A symbol is eligible for deployment. | Passed, active |
| **NO_GO** | A symbol is intentionally not deployed even though the governing process did not fail. | Failed symbol, bad month |
| **Symbol Universe** | The set of symbols under active consideration. | Active pairs, trading pairs |

**`FAIL`** is for process/evidence invalidity; **`NO_GO`** is for symbol non-deployment. Do not use "fail" for both.

## Data construction

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Raw Tick Data** | The canonical timestamped bid/ask tick stream used as the source for bars and replay. | Raw data, history |
| **Tick Bars** | Bars formed by a fixed number of ticks rather than fixed clock time. | Candles, time bars |
| **Feature Set** | The predictor columns derived causally from tick bars for scoring candidate events. | Inputs, signals |
| **Label Set** | The forward-looking target fields derived under causal rules for model evaluation. | Outcomes, targets |

Canonical raw tick parquet schema: `timestamp` (UTC), `bid`, `ask`, `mid`, `spread`, `log_return`.

## Straddle logic (`scripts/boostlss_xs/`)

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Straddle** | A cross-symbol meta-labeling setup that takes a directional primary signal and learns a side/size meta-label. | Setup, signal |
| **Meta-Labeler** | The de-Prado-style secondary model that decides whether to take a primary signal and at what size. | Sizer, filter |
| **BoostLSS Model** | The location-scale-shape boosting model (`boostlss_py`) used for the straddle meta-label distribution. | The model, booster |
| **Walk-Forward (WFO)** | Rolling train/test evaluation where prior periods train the next test period under causal ordering. | Backtest, rolling fit |
| **Causal Validation** | Validation that respects time ordering and forbids look-ahead in features and labels. | OOS check, holdout |

## Runtime operation

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Live Runtime** | The production trading process that runs the FastAPI server + JForex broker adapter. | Live system, production bot |
| **Authoritative Runtime** | The designated local context whose code and credentials are trusted for live operation. | Any worktree, convenient checkout |
| **Warmup** | The historical feature replay used to seed live inference state before current predictions begin. | Backfill, preload |
| **Bar Alignment Ticks** | The tick-count modulus used when sizing **Warmup** loads so the runtime's open-bar accumulator at start matches governance time. | Phase bar ticks, alignment window |
| **Reconciliation** | Matching broker state and local state after restart or drift. | Resync, state repair |
| **Runtime State** | The in-process and persisted state used by the Live Runtime to hold tick bars, feature readiness, trades, and account-risk reservations. | DB, cache, state manager |
| **State Query View** | A read-only view of Runtime State used by business logic that must not depend on table layout or persistence details. | Raw DB access, direct SQL |

> The `/predict` endpoint is currently a **placeholder** returning empty predictions. The candidate-resolution, model-binding, and threshold vocabulary that previously described the OCO runtime is not active in the placeholder and has been removed from this vocabulary.

## Runtime Feature Set contract

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Feature Schema** | The versioned manifest that names the Feature Set, rolling windows, lag rules, and feature definitions. | Feature list, columns tuple |
| **Feature Definition** | A single feature name with its computation group and source dependencies. | Feature metadata, feature row |
| **Model Feature Contract** | The enforceable runtime contract that pins Feature Schema version and Feature Set order. | Feature check, model schema |
| **Feature Computation** | The causal transformation from Tick Bars into the Feature Set. | Feature engineering, dataframe logic |

## Barrier and order lifecycle

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Barrier Scan** | A pending runtime watch created from a selected candidate state that waits for an upper or lower barrier touch. | Pending signal, scan row, setup |
| **Barrier Evaluation** | The completed-bar decision step that advances Barrier Scans and emits Barrier Actions. | Barrier check, scan update |
| **Barrier Action** | A runtime instruction emitted by Barrier Evaluation to open, close, or release a reservation. | Action dict, order signal, event |
| **Barrier State Mutation** | The explicit state transition made to a Barrier Scan during Barrier Evaluation. | Side effect, SQL update |
| **Order Lifecycle** | The Java-side progression from order submission through fill, Python sync, close, and final trade update. | Order flow, trade lifecycle |
| **Order Lifecycle Event** | A broker or local execution event that advances the Order Lifecycle. | Order callback, order message |
| **Worker Queue** | The per-symbol in-memory queue that buffers ticks before Tick Batch submission to Python. | Tick queue, pending queue |
| **Tick Batch** | A per-symbol group of ticks submitted from JForex to the Python runtime for ingestion and bar completion. | Batch, tick payload |
| **Python API Contract** | The Python runtime endpoints, payloads, response shapes, and timeout profiles consumed by JForex. | Bridge protocol, HTTP API |

## Account risk lifecycle

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Account Risk Decision** | The account-level decision that allows or blocks new trading based on account snapshots and limits. | Risk eval, risk check, gate result |
| **Trade Guard Decision** | The per-candidate decision that allows or blocks a selected state based on cost, edge, and reservation capacity. | Trade risk, cost gate |
| **Reservation** | A runtime account-risk allocation held for a selected state until the order opens, closes, expires, or is released. | Risk hold, allocation, pending risk |
| **Reservation Lifecycle** | The allowed progression of a Reservation through pending, open, closed, released, or expired states. | Reservation state machine, risk lifecycle |
| **Entry Gate** | The combined runtime decision that determines whether a selected state may become a Barrier Scan or broker order. | Entry check, allow trading flag |

## Relationships

- **Raw Tick Data** is transformed into **Tick Bars**, which are transformed into the **Feature Set**.
- **Feature Computation** consumes **Tick Bars** and emits the **Feature Set**.
- A **Feature Schema** defines the **Feature Set**, and the **Model Feature Contract** enforces its order.
- The **Straddle** takes a directional primary signal; the **Meta-Labeler** learns side/size; the **BoostLSS Model** is the meta-label distribution; **Walk-Forward (WFO)** + **Causal Validation** evaluate it.
- A selected state may create a **Reservation** and a **Barrier Scan** only after the **Entry Gate** allows it.
- **Barrier Evaluation** consumes a **State Query View** of the latest Tick Bar and produces **Barrier Actions** plus **Barrier State Mutations**.
- An `OPEN_MARKET` **Barrier Action** enters the Java **Order Lifecycle** through the execution adapter.
- The **Worker Queue** forms a **Tick Batch**, and a Tick Batch may complete one or more Tick Bars.
- **Account Risk Decision**, **Trade Guard Decision**, and **Reservation Lifecycle** are separate decisions and must not be collapsed into a single boolean.
- A symbol may be **NO_GO** without the process being a **FAIL**.

## Supporting concepts

These appear in implementation discussion but are not part of the tight canonical vocabulary above:

- "trade lifecycle" for the sequence from setup through execution management
- "model traffic" or "signals" for the stream of live predictions after **Warmup**
- "contract" should be qualified as **Model Feature Contract** or **Python API Contract**
- "state" should be qualified as **Runtime State**, **Barrier Scan**, or **Reservation**
- "action" should be qualified as **Barrier Action** or **Order Lifecycle Event**

## Flagged ambiguities

- "fail" has been used for both process invalidity and symbol exclusion. Use **FAIL** only for process/evidence invalidity, and **NO_GO** for symbol non-deployment.
- "warmup" and "backfill" have been used interchangeably. Prefer **Warmup** for the inference-state replay that seeds live behavior.
- "live" has been used to mean code branch, runtime process, and broker state. Use **Live Runtime** for the running process.
- "risk gate" has blurred account-level and trade-level decisions. Use **Account Risk Decision** for account limits and **Trade Guard Decision** for per-candidate checks.
- "action" is ambiguous between broker commands and barrier outputs. Use **Barrier Action** for runtime lifecycle outputs and **Order Lifecycle Event** for broker/order callbacks.
- "state" is too broad for runtime discussions. Use **Runtime State** for the stored runtime surface, **Barrier Scan** for barrier-tracking rows, and **Reservation** for account-risk allocations.