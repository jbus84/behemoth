from __future__ import annotations

import json
from pathlib import Path


def _load_dashboard() -> dict:
    dashboard_path = Path("provisioning/dashboards/behemoth_jforex.json")
    return json.loads(dashboard_path.read_text(encoding="utf-8"))


def _panels_by_title(dashboard: dict) -> dict[str, dict]:
    panels = dashboard["panels"]
    titles = [panel["title"] for panel in panels]
    assert len(titles) == len(set(titles))
    return {panel["title"]: panel for panel in panels}


def test_jforex_dashboard_contains_demo_certification_panels() -> None:
    dashboard = _load_dashboard()
    panels_by_title = _panels_by_title(dashboard)
    titles = set(panels_by_title)

    assert "JForex Symbol Readiness" in titles
    assert "JForex Entries Allowed" in titles
    assert "JForex Tick Staleness" in titles
    assert "JForex Predict Health" in titles
    assert "JForex Readiness Transitions" in titles
    assert "JForex Readiness Timeouts" in titles

    readiness_panel = panels_by_title["JForex Symbol Readiness"]
    assert "0=COLD" in readiness_panel["description"]
    readiness_mappings = readiness_panel["fieldConfig"]["defaults"]["mappings"][0]["options"]
    assert readiness_mappings["3"]["text"] == "READY"

    staleness_thresholds = panels_by_title["JForex Tick Staleness"]["fieldConfig"]["defaults"][
        "thresholds"
    ]["steps"]
    assert staleness_thresholds[-1]["value"] == 30

    tick_ingest_options = panels_by_title["JForex Tick Ingest Rate"]["options"]
    assert tick_ingest_options["legend"]["displayMode"] == "list"
    assert tick_ingest_options["tooltip"]["mode"] == "multi"

    latency_options = panels_by_title["JForex Predict Latency p95"]["options"]
    assert latency_options["legend"]["displayMode"] == "list"
    assert latency_options["tooltip"]["mode"] == "multi"

    assert panels_by_title["JForex Readiness Transitions"]["targets"][0]["expr"] == (
        "sum by (symbol, from_state, to_state) (rate(behemoth_jforex_live_readiness_transitions_total[5m]))"
    )
    assert panels_by_title["JForex Readiness Timeouts"]["targets"][0]["expr"] == (
        "sum by (symbol) (rate(behemoth_jforex_live_readiness_timeouts_total[5m]))"
    )


def test_open_trades_by_symbol_panel_uses_symbol_summary_layout() -> None:
    dashboard = _load_dashboard()
    panels_by_title = _panels_by_title(dashboard)

    open_trades = panels_by_title["Open Trades by Symbol"]
    assert open_trades["type"] == "table"
    assert open_trades["options"]["sortBy"] == [{"displayName": "Open trades", "desc": True}]

    targets = {target["refId"]: target for target in open_trades["targets"]}
    assert targets["A"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_open_position_age_bars and on(symbol) '
        '(behemoth_broker_open_positions_total > 0)), "metric", '
        '"behemoth_open_position_age_bars", "symbol", ".*")'
    )
    assert targets["B"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_broker_open_positions_total) and on(symbol) '
        '(sum by (symbol) (behemoth_broker_open_positions_total) > 0), "metric", '
        '"behemoth_broker_open_positions_total", "symbol", ".*")'
    )
    assert targets["C"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_open_position_age_seconds and on(symbol) '
        '(behemoth_broker_open_positions_total > 0)), "metric", '
        '"behemoth_open_position_age_seconds", "symbol", ".*")'
    )
    assert targets["D"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_open_position_bars_remaining and on(symbol) '
        '(behemoth_broker_open_positions_total > 0)), "metric", '
        '"behemoth_open_position_bars_remaining", "symbol", ".*")'
    )
    assert all(target["instant"] is True for target in targets.values())

    transformations = open_trades["transformations"]
    add_total = transformations[1]
    add_progress = transformations[2]
    organize = transformations[4]

    assert add_total["id"] == "calculateField"
    assert add_total["options"]["alias"] == "Lifecycle total"
    assert add_progress["id"] == "calculateField"
    assert add_progress["options"]["alias"] == "Progress to expiry"

    rename_map = organize["options"]["renameByName"]
    assert rename_map["symbol"] == "Symbol"
    assert rename_map["behemoth_broker_open_positions_total"] == "Open trades"
    assert rename_map["behemoth_open_position_bars_remaining"] == "Oldest bars remaining"

    overrides = {
        override["matcher"]["options"]: override["properties"]
        for override in open_trades["fieldConfig"]["overrides"]
    }
    open_trades_props = {prop["id"]: prop["value"] for prop in overrides["Open trades"]}
    remaining_props = {prop["id"]: prop["value"] for prop in overrides["Oldest bars remaining"]}
    age_props = {prop["id"]: prop["value"] for prop in overrides["Age (min)"]}

    assert open_trades_props["custom.width"] == 110
    assert open_trades_props["unit"] == "short"
    assert open_trades_props["decimals"] == 0
    assert open_trades_props["custom.cellOptions"]["type"] == "auto"
    assert remaining_props["custom.cellOptions"]["type"] == "auto"
    assert age_props["custom.cellOptions"]["type"] == "auto"


def test_oco_lifecycle_now_panel_uses_current_state_layout() -> None:
    dashboard = _load_dashboard()
    panels_by_title = _panels_by_title(dashboard)

    active_groups_now = panels_by_title["Active groups now"]
    assert active_groups_now["type"] == "stat"
    assert active_groups_now["targets"][0]["expr"] == "sum(behemoth_jforex_active_oco_groups)"
    assert active_groups_now["targets"][0]["instant"] is True

    open_trades_now = panels_by_title["Open trades"]
    assert open_trades_now["type"] == "stat"
    assert open_trades_now["targets"][0]["expr"] == "sum(behemoth_broker_open_positions_total)"
    assert open_trades_now["targets"][0]["instant"] is True

    pending_now = panels_by_title["Pending / canceling"]
    assert pending_now["type"] == "stat"
    assert pending_now["targets"][0]["expr"] == "sum(behemoth_pending_broker_confirm_positions_total)"
    assert pending_now["targets"][0]["instant"] is True

    panel = panels_by_title["OCO Lifecycle Now"]
    assert panel["type"] == "table"
    assert panel["options"]["sortBy"] == [{"displayName": "Active groups", "desc": True}]

    targets = {target["refId"]: target for target in panel["targets"]}
    assert targets["A"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_jforex_active_oco_groups) '
        'and on(symbol) ((sum by (symbol) (behemoth_jforex_active_oco_groups) '
        '+ sum by (symbol) (behemoth_broker_open_positions_total) '
        '+ sum by (symbol) (behemoth_pending_broker_confirm_positions_total)) > 0), '
        '"metric", "behemoth_jforex_active_oco_groups", "symbol", ".*")'
    )
    assert targets["B"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_broker_open_positions_total) '
        'and on(symbol) ((sum by (symbol) (behemoth_jforex_active_oco_groups) '
        '+ sum by (symbol) (behemoth_broker_open_positions_total) '
        '+ sum by (symbol) (behemoth_pending_broker_confirm_positions_total)) > 0), '
        '"metric", "behemoth_broker_open_positions_total", "symbol", ".*")'
    )
    assert targets["C"]["expr"] == (
        'label_replace(sum by (symbol) (behemoth_pending_broker_confirm_positions_total) '
        'and on(symbol) ((sum by (symbol) (behemoth_jforex_active_oco_groups) '
        '+ sum by (symbol) (behemoth_broker_open_positions_total) '
        '+ sum by (symbol) (behemoth_pending_broker_confirm_positions_total)) > 0), '
        '"metric", "behemoth_pending_broker_confirm_positions_total", "symbol", ".*")'
    )

    overrides = {
        override["matcher"]["options"]: override["properties"]
        for override in panel["fieldConfig"]["overrides"]
    }
    active_groups_props = {prop["id"]: prop["value"] for prop in overrides["Active groups"]}
    open_trades_props = {prop["id"]: prop["value"] for prop in overrides["Open trades"]}
    pending_props = {prop["id"]: prop["value"] for prop in overrides["Pending / canceling"]}

    assert active_groups_props["custom.width"] == 110
    assert active_groups_props["decimals"] == 0
    assert open_trades_props["custom.width"] == 110
    assert open_trades_props["decimals"] == 0
    assert open_trades_props["color"] == {"mode": "fixed", "fixedColor": "green"}
    assert pending_props["custom.width"] == 150
    assert pending_props["decimals"] == 0
    assert pending_props["color"] == {"mode": "fixed", "fixedColor": "yellow"}

    transformations = panel["transformations"]
    join = next(t for t in transformations if t["id"] == "joinByLabels")
    assert join["options"]["join"] == ["symbol"]
    assert join["options"]["value"] == "metric"

    organize = next(t for t in transformations if t["id"] == "organize")
    assert organize["id"] == "organize"
    rename_map = organize["options"]["renameByName"]
    assert rename_map["symbol"] == "Symbol"
    assert rename_map["behemoth_jforex_active_oco_groups"] == "Active groups"
    assert rename_map["behemoth_broker_open_positions_total"] == "Open trades"
    assert rename_map["behemoth_pending_broker_confirm_positions_total"] == "Pending / canceling"


def test_makefile_exposes_demo_cert_monitor_target() -> None:
    makefile_path = Path("Makefile")
    makefile = makefile_path.read_text(encoding="utf-8")

    assert "demo-cert-monitor: observability-up" in makefile
    assert '"demo-cert-monitor"' in makefile
    assert '"$(or $(METRICS_PORT),9464)"' in makefile
    assert '"$(or $(REPORT_DIR),data/analysis/backtest_reconcile)"' in makefile
    assert "Monitoring stack: started via make observability-up" in makefile
