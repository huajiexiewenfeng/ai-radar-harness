from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_has_decision_workbench_layout():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert "decision-workbench" in html
    assert "filter-sidebar" in html
    assert "decision-list" in html
    assert "detail-panel" in html
    assert "Human Gate" in html
    assert "renderDecisionList" in html
    assert "renderDetail" in html
