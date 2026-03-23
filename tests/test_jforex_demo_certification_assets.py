from __future__ import annotations

import json
from pathlib import Path


def test_jforex_dashboard_contains_demo_certification_panels() -> None:
    dashboard_path = Path("provisioning/dashboards/behemoth_jforex.json")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panels_by_title = {panel["title"]: panel for panel in dashboard["panels"]}
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

    staleness_thresholds = panels_by_title["JForex Tick Staleness"]["fieldConfig"]["defaults"]["thresholds"]["steps"]
    assert staleness_thresholds[-1]["value"] == 30

    assert panels_by_title["JForex Readiness Transitions"]["targets"][0]["expr"] == (
        "sum by (symbol, from_state, to_state) (rate(behemoth_jforex_live_readiness_transitions_total[5m]))"
    )
    assert panels_by_title["JForex Readiness Timeouts"]["targets"][0]["expr"] == (
        "sum by (symbol) (rate(behemoth_jforex_live_readiness_timeouts_total[5m]))"
    )


def test_makefile_exposes_demo_cert_monitor_target() -> None:
    makefile_path = Path("Makefile")
    makefile = makefile_path.read_text(encoding="utf-8")

    assert "demo-cert-monitor: observability-up" in makefile
    assert '"demo-cert-monitor"' in makefile
    assert '"$(or $(METRICS_PORT),9464)"' in makefile
    assert '"$(or $(REPORT_DIR),data/analysis/backtest_reconcile)"' in makefile
    assert "Monitoring stack: started via make observability-up" in makefile
