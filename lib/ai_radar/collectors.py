from __future__ import annotations

import os
import random
import re
import time
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from ai_radar.timeutil import iso_now, normalize_record_dates


GENERIC_LINK_TITLES = {
    "featured",
    "learn more",
    "read more",
    "see more",
    "view all",
    "blog",
    "news",
    "models",
    "resources",
    "daily papers",
    "papers",
    "datasets",
    "andrew's letter",
    "andrew's letters",
    "data points",
    "ml research",
    "business",
    "science",
    "culture",
    "hardware",
    "ai careers",
    "about",
    "all",
    "older posts",
}

SHOW_MORE_LABELS = ("Show more", "显示更多", "展开", "查看更多")
X_API_BASE_URL = "https://api.x.com/2"


def _clean_text(value: str) -> str:
    text = " ".join(value.split())
    return re.sub(r"\s+([,.;:!?])", r"\1", text).strip()


def _html_to_text(value: str) -> str:
    if "<" not in value or ">" not in value:
        text = _clean_text(value)
    else:
        text = _clean_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))
    return re.sub(r"\s*The post .+? appeared first on .+?\.", "", text).strip()


def _is_article_url(base_url: str, href: str) -> bool:
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return False
    base_path = urlparse(base_url).path.rstrip("/")
    if base_path and base_path != "/" and not parsed.path.startswith(base_path + "/"):
        return False
    return True


def _is_generic_title(title: str) -> bool:
    lowered = title.strip().lower()
    return not lowered or lowered in GENERIC_LINK_TITLES or "@" in lowered


def _is_x_chrome_line(line: str) -> bool:
    value = line.strip()
    if not value:
        return True
    lowered = value.lower()
    if value in {"已置顶", "置顶", "Pinned"}:
        return True
    if value.startswith("@"):
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        return True
    if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", value):
        return True
    if re.fullmatch(r"\d{1,2}月\d{1,2}日", value):
        return True
    if lowered in {"show more", "显示更多"}:
        return True
    return False


def _x_username_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    username = parts[0]
    if username in {"home", "i", "search"}:
        return None
    return username


def build_browser_x_url(source: dict[str, Any]) -> str:
    browser_url = source.get("browser_url")
    if browser_url:
        return str(browser_url)
    username = source.get("username") or _x_username_from_url(str(source.get("url") or ""))
    if username:
        query = quote(f"from:{username}", safe="")
        return f"https://x.com/search?q={query}&src=typed_query&f=live"
    return str(source.get("url"))


def _extract_x_title(text: str) -> str:
    lines = [_clean_text(line) for line in text.splitlines()]
    content_lines = [line for line in lines if not _is_x_chrome_line(line)]
    if len(content_lines) >= 2 and content_lines[1].startswith("@"):
        content_lines = content_lines[2:]
    if content_lines:
        if len(content_lines) > 1 and re.fullmatch(r"[\w .'-]{2,60}", content_lines[0]):
            return content_lines[1][:160]
        return content_lines[0][:160]
    return _clean_text(text)[:160]


def _x_text_is_truncated(text: str) -> bool:
    lowered = text.lower()
    return any(label.lower() in lowered for label in SHOW_MORE_LABELS)


def _x_status_id(url: str) -> str | None:
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


def _x_published_at_from_status_url(url: str) -> str | None:
    status_id = _x_status_id(url)
    if not status_id:
        return None
    try:
        tweet_id = int(status_id)
    except ValueError:
        return None
    twitter_epoch_ms = 1288834974657
    timestamp_ms = (tweet_id >> 22) + twitter_epoch_ms
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def _x_api_datetime(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return value


def records_from_x_api_posts(payload: dict[str, Any], source: dict[str, Any], username: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for post in payload.get("data") or []:
        post_id = str(post.get("id") or "")
        if not post_id:
            continue
        text = str((post.get("note_tweet") or {}).get("text") or post.get("text") or "").strip()
        url = f"https://x.com/{username}/status/{post_id}"
        raw = {
            "source_url": source.get("url"),
            "fetch_method": "x_api",
            "post_id": post_id,
            "referenced_tweets": post.get("referenced_tweets") or [],
            "public_metrics": post.get("public_metrics") or {},
            "entities": post.get("entities") or {},
            "used_note_tweet": bool((post.get("note_tweet") or {}).get("text")),
        }
        records.append(
            normalize_record_dates(
                {
                    "source_id": source["id"],
                    "source_type": source.get("type"),
                    "title": _extract_x_title(text),
                    "url": url,
                    "author": source.get("id"),
                    "published_at": _x_api_datetime(post.get("created_at")) or _x_published_at_from_status_url(url),
                    "captured_at": iso_now(),
                    "text": text[:10000],
                    "raw": raw,
                    "topics": source.get("topics") or [],
                }
            )
        )
    return records


def payload_from_x_mcp_tool_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return json.loads(first["text"])
    raise ValueError("unsupported X MCP payload shape")


def records_from_x_mcp_posts(payload: dict[str, Any], source: dict[str, Any], username: str) -> list[dict[str, Any]]:
    records = records_from_x_api_posts(payload, source, username)
    for record in records:
        record.setdefault("raw", {})["fetch_method"] = "x_mcp"
    return records


def _x_api_get(url: str, token: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def collect_x_api_source(source: dict[str, Any], x_config: dict[str, Any]) -> dict[str, Any]:
    token_env = str(source.get("api_bearer_token_env") or x_config.get("api_bearer_token_env") or "X_API_BEARER_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        return {"status": "unavailable", "records": [], "error": f"missing {token_env}"}
    username = str(source.get("username") or _x_username_from_url(str(source.get("url") or "")) or "")
    user_id = source.get("user_id")
    if not username and not user_id:
        return {"status": "unavailable", "records": [], "error": "missing X username or user_id"}
    timeout = int(x_config.get("api_timeout_seconds", 30))
    base_url = str(x_config.get("api_base_url") or X_API_BASE_URL).rstrip("/")
    try:
        if not user_id:
            user_payload = _x_api_get(
                f"{base_url}/users/by/username/{username}",
                token,
                params={"user.fields": "id,name,username"},
                timeout=timeout,
            )
            user_id = (user_payload.get("data") or {}).get("id")
        if not user_id:
            return {"status": "unavailable", "records": [], "error": "X user lookup returned no id"}
        max_results = int(source.get("max_items_per_fetch", x_config.get("max_items_per_account", 20)))
        params: dict[str, Any] = {
            "max_results": max(5, min(max_results, 100)),
            "exclude": source.get("exclude", x_config.get("exclude", "replies,retweets")),
            "post.fields": "id,text,created_at,author_id,conversation_id,referenced_tweets,public_metrics,entities,note_tweet",
            "expansions": "author_id,referenced_tweets.id",
            "user.fields": "id,name,username",
        }
        payload = _x_api_get(f"{base_url}/users/{user_id}/tweets", token, params=params, timeout=timeout)
    except requests.RequestException as exc:
        return {"status": "unavailable", "records": [], "error": str(exc)}
    records = records_from_x_api_posts(payload, source, username or str(source.get("username") or user_id))
    return {"status": "ok", "records": records}


def _should_fetch_x_detail(text: str, url: str) -> bool:
    lowered = text.lower()
    has_render_noise = "number-flow-react" in lowered or "{line-height" in lowered
    return bool(_x_status_id(url)) and (_x_text_is_truncated(text) or has_render_noise)


def _click_x_show_more(article: Any) -> bool:
    clicked = False
    for label in SHOW_MORE_LABELS:
        try:
            locator = article.get_by_text(label, exact=True)
            if locator.count() > 0:
                locator.first.click(timeout=2000)
                clicked = True
        except Exception:
            continue
    return clicked


def _article_matches_status(article: Any, status_id: str | None) -> bool:
    if not status_id:
        return True
    try:
        return article.locator(f'a[href*="/status/{status_id}"]').count() > 0
    except Exception:
        return False


def _find_x_detail_article(page: Any, status_url: str) -> Any | None:
    status_id = _x_status_id(status_url)
    try:
        articles = page.locator("article").all()
    except Exception:
        return None
    for article in articles:
        if _article_matches_status(article, status_id):
            return article
    return articles[0] if articles else None


def _fetch_x_detail_text(page: Any, status_url: str, fallback_text: str, timeout_ms: int) -> dict[str, Any]:
    try:
        page.goto(status_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("article", timeout=min(timeout_ms, 15000))
        article = _find_x_detail_article(page, status_url)
        if article is None:
            return {"text": fallback_text, "detail_fetched": False, "truncated": _x_text_is_truncated(fallback_text)}
        _click_x_show_more(article)
        text = article.inner_text(timeout=5000).strip()
        if not text:
            return {"text": fallback_text, "detail_fetched": False, "truncated": _x_text_is_truncated(fallback_text)}
        return {"text": text[:10000], "detail_fetched": True, "truncated": _x_text_is_truncated(text)}
    except Exception as exc:
        return {
            "text": fallback_text,
            "detail_fetched": False,
            "truncated": _x_text_is_truncated(fallback_text),
            "detail_error": str(exc).splitlines()[0],
        }


def _html_candidate_title(article: Any, link: Any) -> str:
    for heading in article.find_all(["h1", "h2", "h3", "h4"]):
        title = _clean_text(heading.get_text(" ", strip=True))
        if not _is_generic_title(title):
            return title
    return _clean_text(link.get_text(" ", strip=True) or link.get("aria-label", ""))


def _launch_chromium_context(playwright: Any, profile_dir: Path, x_config: dict[str, Any], headless: bool = True) -> Any:
    options: dict[str, Any] = {
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
    }
    executable_path = x_config.get("chrome_executable_path")
    if executable_path:
        options["executable_path"] = executable_path
    return playwright.chromium.launch_persistent_context(str(profile_dir), **options)


def _profile_is_in_use(profile_dir: Path) -> bool:
    lockfile = profile_dir / "lockfile"
    if not lockfile.exists():
        return False
    try:
        with lockfile.open("a+b"):
            return False
    except PermissionError:
        return True


def _rss_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _atom_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return value.replace("Z", "+00:00")
    except AttributeError:
        return None


def _find_atom_text(entry: ET.Element, name: str) -> str:
    value = entry.findtext(f"{{http://www.w3.org/2005/Atom}}{name}") or entry.findtext(name) or ""
    return value.strip()


def _collect_atom_entries(source_id: str, root: ET.Element, captured: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
    for entry in entries:
        title = _find_atom_text(entry, "title")
        link = ""
        for link_node in entry.findall("{http://www.w3.org/2005/Atom}link") + entry.findall("link"):
            href = link_node.attrib.get("href")
            if href:
                link = href
                break
        summary = _html_to_text(_find_atom_text(entry, "summary") or _find_atom_text(entry, "content"))
        author = entry.findtext("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name") or entry.findtext("author/name")
        updated = _find_atom_text(entry, "updated") or _find_atom_text(entry, "published")
        if title and link:
            records.append(
                normalize_record_dates(
                    {
                    "source_id": source_id,
                    "title": title,
                    "url": link,
                    "author": author,
                    "published_at": _atom_time(updated),
                    "captured_at": captured,
                    "text": summary[:10000],
                    "raw": {"updated": updated},
                    }
                )
            )
    return records


def collect_rss_from_text(source_id: str, xml_text: str, captured_at: str | None = None) -> list[dict[str, Any]]:
    captured = captured_at or iso_now()
    root = ET.fromstring(xml_text)
    records: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = _html_to_text(item.findtext("description") or "")
        pub_date = item.findtext("pubDate")
        if title and link:
            records.append(
                normalize_record_dates(
                    {
                    "source_id": source_id,
                    "title": title,
                    "url": link,
                    "author": None,
                    "published_at": _rss_time(pub_date),
                    "captured_at": captured,
                    "text": description[:10000],
                    "raw": {"pubDate": pub_date},
                    }
                )
            )
    if not records:
        records.extend(_collect_atom_entries(source_id, root, captured))
    return records


def collect_html_from_text(source_id: str, base_url: str, html_text: str, captured_at: str | None = None) -> list[dict[str, Any]]:
    captured = captured_at or iso_now()
    soup = BeautifulSoup(html_text, "html.parser")
    records: list[dict[str, Any]] = []
    for article in soup.find_all(["article", "li", "div"]):
        link = article.find("a", href=True)
        if not link:
            continue
        if not _is_article_url(base_url, link["href"]):
            continue
        title = _html_candidate_title(article, link)
        if _is_generic_title(title):
            continue
        links = article.find_all("a", href=True)
        text = _clean_text(article.get_text(" ", strip=True))
        if len(links) > 3 or len(text) > 1500:
            continue
        records.append(
            normalize_record_dates(
                {
                "source_id": source_id,
                "title": title,
                "url": urljoin(base_url, link["href"]),
                "author": None,
                "published_at": None,
                "captured_at": captured,
                "text": text[:10000],
                "raw": {},
                }
            )
        )
        if len(records) >= 20:
            break
    return records


def collect_http_source(source: dict[str, Any]) -> dict[str, Any]:
    fetch_method = source["fetch_method"]
    url = source["feed_url"] if fetch_method == "rss" else source["url"]
    response = requests.get(url, timeout=20, headers={"User-Agent": "AI-Radar/0.1"})
    response.raise_for_status()
    if fetch_method == "rss":
        records = collect_rss_from_text(source["id"], response.text)
    else:
        records = collect_html_from_text(source["id"], source["url"], response.text)
    for record in records:
        record["source_type"] = source.get("type")
        record["topics"] = source.get("topics") or []
    return {"status": "ok", "records": records[: source.get("max_items_per_fetch", 20)]}


def collect_x_source(source: dict[str, Any], x_config: dict[str, Any]) -> dict[str, Any]:
    profile_dir = Path(x_config.get("profile_dir", "../.browser-profile"))
    if not profile_dir.exists():
        return {"status": "unavailable", "records": [], "error": "Playwright profile directory does not exist"}
    if _profile_is_in_use(profile_dir):
        return {"status": "unavailable", "records": [], "error": "profile_in_use"}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"status": "unavailable", "records": [], "error": "Playwright is not installed"}
    max_items = int(source.get("max_items_per_fetch", x_config.get("max_items_per_account", 20)))
    timeout_ms = int(x_config.get("stage_timeout_minutes", 5)) * 60 * 1000
    records: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        context = _launch_chromium_context(playwright, profile_dir, x_config, headless=True)
        page = context.new_page()
        try:
            browser_url = build_browser_x_url(source)
            page.goto(browser_url, wait_until="domcontentloaded", timeout=timeout_ms)
            if "/login" in page.url or page.locator('input[autocomplete="username"]').count() > 0:
                context.close()
                return {"status": "session_expired", "records": [], "error": "X login session expired"}
            page.wait_for_timeout(3000)
            candidates: list[dict[str, Any]] = []
            for article in page.locator("article").all()[:max_items]:
                text = article.inner_text(timeout=3000).strip()
                if not text:
                    continue
                links = article.locator('a[href*="/status/"]')
                href = links.first.get_attribute("href") if links.count() else source["url"]
                times = article.locator("time")
                published_at = times.first.get_attribute("datetime") if times.count() else None
                url = urljoin("https://x.com", href)
                candidates.append({"text": text, "url": url, "published_at": published_at or _x_published_at_from_status_url(url)})
            detail_page = context.new_page()
            for candidate in candidates:
                if _should_fetch_x_detail(candidate["text"], candidate["url"]):
                    detail = _fetch_x_detail_text(detail_page, candidate["url"], candidate["text"], min(timeout_ms, 30000))
                else:
                    detail = {"text": candidate["text"], "detail_fetched": False, "truncated": False}
                text = detail["text"]
                raw = {
                    "source_url": source["url"],
                    "browser_url": browser_url,
                    "detail_fetched": detail["detail_fetched"],
                    "truncated": detail["truncated"],
                }
                if detail.get("detail_error"):
                    raw["detail_error"] = detail["detail_error"]
                records.append(
                    normalize_record_dates(
                        {
                        "source_id": source["id"],
                        "source_type": source.get("type"),
                        "title": _extract_x_title(text),
                        "url": candidate["url"],
                        "author": source.get("id"),
                        "published_at": candidate["published_at"],
                        "captured_at": iso_now(),
                        "text": text[:10000],
                        "raw": raw,
                        "topics": source.get("topics") or [],
                        }
                    )
                )
            detail_page.close()
            time.sleep(random.uniform(2, 5))
            return {"status": "ok", "records": records}
        finally:
            context.close()
