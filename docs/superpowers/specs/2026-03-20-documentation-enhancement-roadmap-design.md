# Documentation Enhancement Roadmap Design

## Purpose

Define a prioritized roadmap for improving the documentation corpus across reader experience, authority clarity, navigation, operator usefulness, generation quality, and compatibility governance.

This is a roadmap design, not an implementation plan for a single patch set. Its purpose is to sequence future work so documentation changes improve understanding first, then durability, then long-tail corpus hygiene.

## Recommended Roadmap Structure

Use a user-journey-first roadmap rather than a generator-first or platform-first roadmap.

Why this approach:
- it improves the first-read experience for operators and new contributors
- it still includes validation and generation guardrails
- it prevents internal cleanup work from outrunning reader-visible value

## Priority Bands

### Now

1. Entrypoints and Orientation
2. Authority Hierarchy and Truth Sources
3. Navigation and Taxonomy

These themes should be treated as one coordinated band. Together they determine whether a reader can form the correct model of the active system and locate the right evidence.

### Next

4. Operator Decision Support
5. Generation Quality and Guardrails

These themes improve day-to-day operational usefulness and prevent regression after the first cleanup wave lands.

### Later

6. Archive and Compatibility Governance

This theme matters, but it should follow once the active-path narrative and classification model are stable.

## Roadmap Themes

### 1. Entrypoints and Orientation

Objective:
Make the first five minutes of the docs unambiguous for both operators and new contributors.

Desired outcomes:
- readers can identify the active system without ambiguity
- readers can distinguish active vs compatibility material early
- readers know where to go next based on their role

Candidate enhancements:
- build a single "start here" route for new contributors and operators
- add an "active system at a glance" block to major landing pages
- standardize "read this next" sections on top-level docs
- add concise glossary-style clarification for recurring terms such as `stage snapshot`, `reduced core`, `candidate`, `compatibility`, and `docs contract`

### 2. Authority Hierarchy and Truth Sources

Objective:
Make document authority explicit so readers can tell what defines the system, what reports evidence, and what is only compatibility or historical material.

Desired outcomes:
- canonical, generated, interpretive, candidate, compatibility, and archive material are clearly distinguished
- readers can move from interpretation to source artifacts without guesswork
- important reports explain where their truth comes from

Candidate enhancements:
- add authority banners or metadata blocks to major docs
- standardize repo-wide rules for canonical vs generated vs interpretive docs
- make stage snapshots and governed manifests visibly authoritative where appropriate
- add cross-links from interpretive reports back to the source-of-truth artifacts they summarize

### 3. Navigation and Taxonomy

Objective:
Align site navigation, generated indexes, and taxonomy rules so active and non-active documentation do not compete for the same reader attention.

Desired outcomes:
- active operations and contributor routes are easier to find
- compatibility, candidate, and archive material are still reachable but clearly lower-prominence
- generated index pages and `mkdocs` navigation reflect the same conceptual model

Candidate enhancements:
- rework `mkdocs.yml` around reader intent rather than raw file families
- separate active operations, contributor orientation, evidence/reports, compatibility, candidate, and archive material
- make generated index pages mirror the same taxonomy as the site nav
- reduce duplicate paths to the same material under conflicting labels

### 4. Operator Decision Support

Objective:
Turn operational documents into decision-support surfaces rather than passive report listings.

Desired outcomes:
- operators can answer "is this deployable?" and "what action is required next?" quickly
- blockers, monitored risks, and data gaps are described consistently
- operational docs link directly to the governed artifacts behind their claims

Candidate enhancements:
- rewrite key operational pages around decisions, prerequisites, blockers, and next actions
- add explicit go/no-go sections where current docs mostly list evidence
- standardize terminology for blocking conditions, monitored risks, and missing artifacts
- link operator-facing pages to the specific stage artifacts and governance rows they depend on

### 5. Generation Quality and Guardrails

Objective:
Prevent recurring documentation errors from generators, builders, and publication routines.

Desired outcomes:
- generated docs cannot silently drift on title, symbol, runtime label, or taxonomy
- published docs do not show empty or misleading generated sections without explanation
- generated pages expose enough metadata to support validation and classification

Candidate enhancements:
- add automated checks for title, symbol, and runtime-label consistency
- add checks for empty published sections and placeholder-style output
- add taxonomy/classification validation for generated catalog pages
- add a small metadata contract for generated docs declaring symbol, runtime, authority class, and provenance

### 6. Archive and Compatibility Governance

Objective:
Define publication and lifecycle policy for compatibility, legacy, candidate, and archive surfaces.

Desired outcomes:
- compatibility material remains available without confusing the active-path story
- readers can tell whether a document is historical evidence, active compatibility guidance, or deprecated runtime material
- stale report families do not accumulate indefinitely without status

Candidate enhancements:
- define qualification rules for `compatibility`, `legacy`, `candidate`, and `archive`
- decide which compatibility families remain published by default and which move behind lower-prominence navigation
- add retention and deprecation rules for old report families
- label historically useful evidence differently from deprecated runtime guidance

## Suggested Sequencing Logic

1. Fix first-read comprehension.
2. Fix authority boundaries.
3. Make navigation enforce that model.
4. Improve operator decision usability.
5. Add generator/process checks so the improvements hold.
6. Resolve long-tail compatibility and archive policy.

This sequencing avoids preserving today’s ambiguity in automation checks or archive policy.

## Success Criteria

The roadmap is succeeding when:
- a new contributor can identify the active system and reading path quickly
- an operator can find go/no-go documentation without wading through compatibility debris
- major docs declare their authority role clearly
- site navigation and generated indexes classify docs consistently
- generated documentation errors are caught automatically before publication
- legacy and compatibility material remain available without dominating the active narrative

## Non-Goals

This roadmap does not by itself:
- commit to a full immediate `mkdocs` overhaul
- require removal of all compatibility documentation
- collapse all generated report families into a new format
- replace the existing docs contract with a wholly new framework

Those may become follow-on projects, but they should be scoped separately.

## Recommended Next Step

Convert this roadmap into one or more execution plans, starting with a concrete `Now`-band work package:
- entrypoints and orientation
- authority hierarchy and truth-source labeling
- navigation and taxonomy alignment
