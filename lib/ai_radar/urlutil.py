from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in TRACKING_KEYS or any(lower_key.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        query_pairs.append((key, value))
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def urlhash(url: str, length: int = 16) -> str:
    canonical = canonicalize_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]


def urlhash8(url: str) -> str:
    return urlhash(url, 8)


def item_id_for(run_date: str, url: str) -> str:
    return f"{run_date}-{urlhash8(url)}"
