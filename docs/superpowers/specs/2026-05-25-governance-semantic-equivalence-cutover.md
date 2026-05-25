# Governance Cutover Equivalence Bar

Target branch: `governance-framework`
Target commit: `9df9f6ab`

## Decision

Phase 1g accepts semantic equivalence as the migration cutover bar for OCO governance artifacts.

Raw byte-identical parity remains a diagnostic check, but it is not the blocking gate for this cutover. The byte parity test stays marked `xfail` until real frozen reference artifacts are captured from the authoritative runtime environment.

## Rationale

The legacy OCO scripts and the unified governance pipeline can serialize equivalent evidence with harmless formatting drift, including CSV column order, JSON key order, and float representation. The cutover gate therefore verifies canonical artifact meaning rather than raw bytes.

The semantic comparison is intentionally strict about governance content:

- CSV fixtures are compared after canonical ordering and numeric tolerance handling.
- JSON fixtures are compared after stable key ordering and canonicalization.
- Empty artifacts must preserve the same schema and governance meaning.
- Required verdict vocabulary remains canonical: `PASS`, `FAIL`, `GO`, and `NO_GO`.

## Fixture Status

`tests/governance/fixtures/synthetic_oco_reference/` is a comparator mechanics fixture only. It is not Certification Evidence and must not be used to claim production byte parity.

When real frozen OCO artifacts are available from the authoritative runtime environment, copy them into the reference fixture location and remove the byte-parity `xfail`.
