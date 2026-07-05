from __future__ import annotations

from ai_radar.render import render_daily_report, render_dashboard_data


def test_report_shows_content_and_capture_dates():
    report = render_daily_report(
        "2026-07-04",
        [
            {
                "title": "Timed item",
                "source_id": "test",
                "source_type": "company_official",
                "url": "https://example.com/timed",
                "content_type": "model_release",
                "summary": "摘要",
                "why_it_matters": "原因",
                "publish_score": 4,
                "learning_score": 3,
                "daily_rank": 5,
                "learning_rank": 4,
                "status": "candidate",
                "article_angles": [],
                "learning_notes": [],
                "published_at": "2026-07-04T02:00:00+00:00",
                "content_date": "2026-07-04",
                "captured_at": "2026-07-05T08:00:00+08:00",
                "date_confidence": "exact",
            }
        ],
        {"status": "complete", "source_status": "ok", "llm_status": "disabled", "x_status": "ok", "failed_sources": []},
    )

    assert "内容日期：2026-07-04" in report
    assert "发布时间：2026-07-04T02:00:00+00:00" in report
    assert "采集时间：2026-07-05T08:00:00+08:00" in report


def test_daily_report_includes_coverage_and_budget():
    run = {
        "status": "complete",
        "source_status": "ok",
        "llm_status": "disabled",
        "x_status": "not_configured",
        "failed_sources": [],
        "coverage": {"openai_news": "full", "anthropic_blog": "none"},
        "budget": {"phase1": {"discarded": 2}, "global": {"max_human_review_items": 30}},
    }

    text = render_daily_report("2026-07-05", [], run)

    assert "## 来源覆盖" in text
    assert "`openai_news`：full" in text
    assert "## 预算消耗" in text
    assert "Human Gate 上限：30" in text


def test_dashboard_data_includes_coverage_and_budget(tmp_path):
    data = render_dashboard_data(
        "2026-07-05",
        [],
        {"coverage": {"openai_news": "full"}, "budget": {"phase1": {"discarded": 1}}},
        {},
        [],
        root=tmp_path,
    )

    assert '"coverage": {' in data
    assert '"budget": {' in data
