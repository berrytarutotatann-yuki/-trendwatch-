"""arXiv（論文の公開 API、登録不要。3秒に1回まで）。"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date

from .. import http

log = logging.getLogger(__name__)
BASE = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom",
      "arxiv": "http://arxiv.org/schemas/atom",
      "os": "http://a9.com/-/spec/opensearch/1.1/"}
PAGE = 1000


def parse_feed(xml_text: str) -> tuple[int, list[dict]]:
    root = ET.fromstring(xml_text)
    total_el = root.find("os:totalResults", NS)
    if total_el is None or total_el.text is None:
        raise ValueError("arXiv: 総件数のない応答")
    total = int(total_el.text)
    entries = []
    for e in root.findall("a:entry", NS):
        eid = (e.findtext("a:id", default="", namespaces=NS) or "").strip()
        if "api/errors" in eid:
            raise ValueError("arXiv API エラー")
        if not eid:
            continue
        title = re.sub(r"\s+", " ", e.findtext("a:title", default="", namespaces=NS) or "").strip()
        published = (e.findtext("a:published", default="", namespaces=NS) or "")[:10]
        authors = [a.findtext("a:name", default="", namespaces=NS) for a in e.findall("a:author", NS)]
        cats = [c.get("term") for c in e.findall("a:category", NS) if c.get("term")]
        entries.append({"id": eid, "title": title, "published": published,
                        "first_author": authors[0] if authors else "", "categories": cats})
    return total, entries


def _query_all(search_query: str, limit: int = 5000) -> list[dict] | None:
    out: list[dict] = []
    start = 0
    while start < limit:
        r = http.get(BASE, params={"search_query": search_query, "start": start,
                                   "max_results": PAGE, "sortBy": "submittedDate",
                                   "sortOrder": "descending"})
        if r is None or r.status_code != 200:
            log.warning("arXiv 取得失敗: %s", search_query)
            return None
        try:
            total, entries = parse_feed(r.text)
        except (ET.ParseError, ValueError):
            log.warning("arXiv: 不正な応答")
            return None
        out.extend(entries)
        start += PAGE
        if len(out) >= total:
            return out
        if not entries:
            return None
    if len(out) < total:
        log.warning("arXiv: 取得上限を超えました")
        return None
    return out


def _range(start: date, end: date) -> str:
    return f"submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"


def fetch_day(day: date, categories: list[str]) -> list[dict]:
    if not categories:
        return []
    cats = " OR ".join(f"cat:{c}" for c in categories)
    entries = _query_all(f"({cats}) AND {_range(day, day)}")
    if entries is None:
        raise RuntimeError("arXiv 取得失敗")
    return [{"source": "arxiv", "id": f"arxiv:{e['id'].rsplit('/', 1)[-1]}",
             "title": e["title"], "voice": e["first_author"],
             "categories": e["categories"]} for e in entries]


def term_daily_counts(term: str, start: date, end: date) -> dict[str, dict] | None:
    q = f'(ti:"{term}" OR abs:"{term}") AND {_range(start, end)}'
    entries = _query_all(q)
    if entries is None:
        return None
    counts: dict[str, int] = defaultdict(int)
    voices: dict[str, set] = defaultdict(set)
    for e in entries:
        d = e["published"]
        if not d:
            continue
        counts[d] += 1
        voices[d].add(e["first_author"])
    return {d: {"count": counts[d], "voices": len(voices[d])} for d in counts}
