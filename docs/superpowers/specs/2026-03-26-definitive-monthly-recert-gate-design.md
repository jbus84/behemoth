# Definitive Monthly Recert Gate Design

## Goal

Make `make monthly-recert` the single definitive release gate for monthly candidate promotion. The command must always execute the full parity/certification chain needed to reduce ambiguity before live capital is exposed.

## Current Problem

Current `main` already treats `monthly-recert` as the operator entrypoint for Dukascopy-candidate recertification, but it only guarantees:

1. candidate artifact sync
2. real Dukascopy JForex matrix
3. full Stage 14 certification summary

That leaves a gap: local surrogate parity is available in the repo, but it is not part of the required recert path. This creates room for drift between the real tester path and the local surrogate path, and makes it possible for issues to pass one surface while remaining undetected on the other.

There is also a transport-fidelity issue. Certification-sensitive settings such as tick batching can materially affect parity. If those settings are left to operator memory or ad hoc overrides, the repo no longer has one authoritative definition of a “strict” recert run.

## Policy Change

`make monthly-recert` becomes the canonical definitive recertification gate.

It must always run, in order:

1. candidate artifact sync
2. `make jforex-dukascopy-matrix`
3. `make local-jforex-parity-matrix`
4. `make full-stage14-cert`

The command is intentionally strict and intentionally slower than a debugging-only or convenience wrapper. The purpose is not operator convenience; it is maximum confidence before promotion and live trading.

There should be no alternate “fast default” hidden behind the same command. If the repo needs lighter debugging commands, they should remain separate and explicit.

## Concrete Changes

### `scripts/run_monthly_recert.py`

Update the script so that:

- the docstring explicitly describes `monthly-recert` as the definitive recertification gate
- candidate artifact sync remains the first step
- `make local-jforex-parity-matrix` is added as a mandatory step after `make jforex-dukascopy-matrix`
- certification batching is pinned with an explicit constant:
  - `CERT_TICK_BATCH_SIZE = "1"`
- both matrix commands receive `TICK_BATCH_SIZE=1`
- step labels reflect the three-step parity/cert chain after sync

This makes the stricter behavior explicit in code instead of relying on undocumented operator habit.

### `tests/test_run_monthly_recert.py`

Add or update unit coverage so the script contract is enforced:

- `monthly-recert` must run:
  1. `jforex-dukascopy-matrix`
  2. `local-jforex-parity-matrix`
  3. `full-stage14-cert`
- both matrix invocations must include `TICK_BATCH_SIZE=1`
- the existing summary/go-no-go behavior remains unchanged

## Non-Goals

- Do not introduce optional bypass flags in this change.
- Do not create a second “strict” variant such as `monthly-recert-strict`.
- Do not change the surrounding promote-live workflow in this design.
- Do not mix this policy change with unrelated parity-contract fixes.

## Error Handling

Failure semantics remain strict:

- if candidate sync fails, exit immediately
- if either matrix step fails, exit immediately
- if Stage 14 certification fails, exit immediately
- if critical certification checks fail, the script still exits non-zero after printing the per-symbol summary

This preserves the existing fail-fast shape while strengthening the gate definition.

## Verification

Minimum verification for implementation:

1. `uv run pytest -q tests/test_run_monthly_recert.py`

Success criteria:

- there is one authoritative `monthly-recert` path
- that path always includes both real Dukascopy and local surrogate parity runs
- certification batching is pinned in code for both matrix steps
- the stricter behavior is obvious from the script itself, not just from tribal knowledge

## Rationale

The repo is already trying to be definitive about deployment and governance. Allowing recertification to omit one of the available parity surfaces weakens that stance and increases the chance that discrepancies reach live trading. Folding both parity surfaces into the single release gate is the simplest way to keep the process aligned with the repo’s stated safety posture.
