# ADR 0002: Multi-Family Bundle Contract

- Status: Accepted
- Date: 2026-05-26
- Supersedes parts of: ADR 0001

## Context

ADR 0001 fixed bundle pathing but baked the OCO family into `BUNDLE_LAYOUT` (`{symbol_lower}_oco_locked_predictions.parquet`, etc.). Non-OCO mining outcomes -- single-barrier first-touch, breakout, momentum -- cannot be expressed as bundles today, even though the reader side (`BundlePaths.from_lock`) is already family-agnostic.

## Decision

1. Every `*_live_lock.json` conforms to `schema_version: 3`.
2. v3 adds a required `bundle.family: str` field identifying the mining outcome the bundle was produced for.
3. `BUNDLE_LAYOUT` is replaced by `BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]]`, keyed by family. Filename templates within each layout MAY include the family name; they MUST NOT hardcode any family they don't claim.
4. A new helper `bundle_layout_for(family: str) -> tuple[BundleArtifactSpec, ...]` is the only sanctioned lookup. Unknown families raise `BundleIntegrityError`.
5. Producers (`freeze_oco_live_governance.py`, `freeze_oco_historical_governance.py`) accept the family they are freezing for and use the matching layout.
6. The lock filename suffix remains `_live_lock.json` (no family in the filename); discrimination happens via `bundle.family` after reading.
7. There is no fallback for missing or unknown families. Stale v1 or v2 locks fail loud and must be migrated.

## Consequences

- One-shot migration converts existing v2 locks to v3 by inserting `bundle.family: "oco_first_touch_clean"`.
- Adding a new family means adding one row to `BUNDLE_LAYOUTS` and producing bundles via the existing freeze tooling. No consumer changes required.
- The OCO assumption is removed from path resolution; it remains only in glob/filename patterns at consumer sites -- those are handled in a separate ADR.
