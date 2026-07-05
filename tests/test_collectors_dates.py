from __future__ import annotations

from ai_radar.collectors import _x_published_at_from_status_url, collect_html_from_text, collect_rss_from_text


def test_rss_records_include_content_date():
    records = collect_rss_from_text(
        "test_rss",
        """
        <rss><channel><item>
          <title>Important AI release</title>
          <link>https://example.com/release</link>
          <pubDate>Fri, 04 Jul 2026 01:30:00 GMT</pubDate>
          <description>Release notes</description>
        </item></channel></rss>
        """,
        captured_at="2026-07-05T08:00:00+08:00",
    )

    assert records[0]["published_at"] == "2026-07-04T01:30:00+00:00"
    assert records[0]["content_date"] == "2026-07-04"
    assert records[0]["date_confidence"] == "exact"


def test_html_records_without_date_are_explicitly_unknown():
    records = collect_html_from_text(
        "test_html",
        "https://example.com/news",
        """
        <html><body>
          <article>
            <a href="/news/story">Important AI story</a>
            <p>No machine-readable publish date here.</p>
          </article>
        </body></html>
        """,
        captured_at="2026-07-05T08:00:00+08:00",
    )

    assert records[0]["published_at"] is None
    assert records[0]["content_date"] is None
    assert records[0]["date_confidence"] == "unknown"


def test_x_status_id_decodes_publish_time():
    published_at = _x_published_at_from_status_url("https://x.com/AndrewYNg/status/2049886895530967534")

    assert published_at == "2026-04-30T16:21:35+00:00"
