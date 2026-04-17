# Open Trade Grafana Visualization Design

**Date:** 2026-04-17  
**Status:** Approved

## Problem

The current `Open Positions` section in the provisioned JForex Grafana dashboard is hard to interpret during live monitoring. The existing table merges multiple instant Prometheus queries into a color-filled grid, which creates three operator problems:

- labels are truncated, so column meaning is not obvious at a glance
- color is applied to too many cells, so urgency is not visually focused
- operators must mentally combine elapsed bars, remaining bars, and age to decide which open trade needs attention

The user wants this section optimized for interpretation, with richer detail for currently open trades rather than maximum density across all symbols.

## Goal

Turn the open-trade area into a compact status summary for currently open trades, where the most urgent positions are immediately obvious.

## Non-Goals

- No changes to Prometheus metric names or backend metric generation
- No changes to Python API or JForex runtime behavior
- No attempt to redesign the full dashboard outside the open-trade section
- No synthetic placeholder rows when there are no open trades

## Current State

The relevant dashboard section lives in `provisioning/dashboards/behemoth_jforex.json` and currently includes:

- `Open Positions (total)` stat panel
- `Open Positions` table panel

The table panel currently joins these instant queries:

- `behemoth_open_position_age_bars > 0`
- `behemoth_open_position_bars_remaining > 0`
- `behemoth_open_position_age_seconds / 60 > 0`

It then displays those values as background-colored table cells, sorted by `Bars remaining`.

## Chosen Approach

Keep the section as a small coordinated panel cluster, but redesign the table into a timeline-oriented status board.

### Panel 1: Open Positions (total)

Retain the existing count stat panel as the fast top-level indicator for whether any trades are currently open.

### Panel 2: Open Positions Timeline Table

Replace the current heatmap-like table presentation with a clearer table that emphasizes expiry proximity.

The table should show:

- `Symbol`
- `Bars remaining`
- `Age (min)`
- `Progress to expiry`

The dominant visual cue should be `Progress to expiry`, not background color on every numeric cell. Numeric values should remain readable as plain text.

## Information Hierarchy

The operator should be able to answer these questions in order:

1. Are there any open positions?
2. Which open trade is closest to expiry?
3. How old is that trade?
4. How far through its lifecycle is it relative to the allowed holding window?

To support that hierarchy:

- the stat panel answers question 1
- the table is sorted by lowest `Bars remaining` first to answer question 2
- `Age (min)` provides supporting context for question 3
- the progress visualization answers question 4 without mental arithmetic

## Visual Design Rules

- Remove background color fills from the numeric `Bars remaining` and `Age (min)` cells
- Use color narrowly and semantically, only where it helps interpret urgency
- Expand the open-trade table panel beyond its current width so column headers and progress are legible
- Keep the table readable when only one or two trades are open, since that is the expected primary use case

Urgency semantics:

- green: comfortably early in the holding window
- yellow: approaching expiry
- red: near expiry

## Grafana Implementation

All implementation remains in `provisioning/dashboards/behemoth_jforex.json`.

### Query Model

Keep the panel in instant-query mode and continue using the existing open-position metrics. No backend changes are required.

The redesigned table will continue to rely on:

- elapsed bars
- remaining bars
- age in minutes

The presentation layer should transform those values into a visually ranked timeline table. The exact Grafana transformation and field-configuration mechanics can be adjusted during implementation, but the behavior must remain:

- symbol keyed
- instant query based
- sorted by lowest remaining bars first

### Layout

The open-trade section should remain a two-panel cluster:

- a small total-count stat panel
- a wider table panel for per-trade detail

The table panel should receive more horizontal space than its current `8x8` slot so the section no longer truncates headers or compresses the progress display.

## Empty-State Behavior

If there are no open trades:

- the total stat should show zero
- the table may render empty
- no synthetic rows, placeholder text rows, or fake progress bars should be introduced

## Testing And Verification

Verification for this change is dashboard-focused:

- confirm the Grafana JSON parses successfully
- confirm the modified panel queries remain instant-mode
- confirm the table still sorts by lowest `Bars remaining`
- visually verify in Grafana that the section is easier to interpret with live metrics

No Prometheus metric or runtime verification changes are required because the data source contract is unchanged.

## Implementation Boundary

This design is intentionally narrow. It authorizes changes to the open-trade Grafana presentation only. If implementation reveals that Grafana cannot express the progress visualization cleanly with the current metric shape, that should be treated as a design feedback point before adding new backend metrics.
