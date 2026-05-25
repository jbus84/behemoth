# ADR 0001: Deterministic Month Bundles

- Status: Accepted
- Date: 2026-05-25

## Context

Month build bundles under `configs/research/governance/oco_candidate_builds/<YYYY-MM>/` historically mixed three different path conventions in a single `*_oco_live_lock.json`:

1. Absolute machine-specific paths (e.g. `/Users/<name>/repositories/behemoth/...`), inserted by `run_monthly_build.py::_materialize_bundle_models`.
2. Bundle-relative paths to frozen artifacts (`predictions_path`, `reduced_states_csv_path`).
3. Repo-relative paths to mutable mining outputs under `data/analysis/tick_opportunity_mining_dukascopy_candidate/` and `models/oco_dukascopy_candidate/`.

Stage 12 and `run_monthly_recert` evolved fallback branches that would prefer the bundle copy and fall back to the mining output. The fallback masked the fact that a "frozen" lock was not actually frozen, and led to PR #238 hardening existence checks instead of fixing the contract.

## Decision

1. Every `*_oco_live_lock.json` conforms to `schema_version: 2`.
2. In v2 every `artifacts.<key>.path` is **bundle-relative** (relative to the directory containing the lock).
3. Every referenced artifact physically lives inside the bundle directory; bundles are self-contained.
4. The lock stores **only** the load path in `artifacts.*`; the original source location is preserved as metadata in a separate `provenance.*` block and is never opened by certification or runtime code.
5. All path resolution goes through `src/behemoth/core/bundle_paths.py::BundlePaths`. No script may concatenate a lock string with a repo root.
6. `scripts/validate_bundle.py` is the single source of truth for bundle integrity and runs in CI on every bundle.
7. There is no fallback to mining outputs at certification time. Missing artifacts fail loudly with `incomplete bundle` errors.

## Consequences

- One-shot migration is required for existing bundles (2026-02, 2026-03, 2026-04).
- The legacy `source_predictions_path` and `train_predictions_path` keys are removed; their values are preserved under `provenance.predictions.origin` and `provenance.train_predictions.origin`.
- The PR #238 fallback in `run_stage12_stage13_certification.py` and the existence checks in `run_monthly_recert.py` are deleted in the same change that introduces v2.
- Bundles become byte-stable and portable: any developer can reproduce certification from a bundle alone.
