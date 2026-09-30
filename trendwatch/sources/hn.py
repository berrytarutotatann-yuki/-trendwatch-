"""Hacker News（Algolia の公開検索 API、登録不要）。"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from .. import http
from . import day_bounds, ts_to_day

log = logging.getLogger(__name__)
BASE = "https://hn.algolia.com/api/v1/search_by_date"
PAGE = 1000  # Algolia は1回の検索で最大1000件まで


def _search(params: dict, lo: int, hi: int) -> list[dict] | None:
    """[lo, hi) の期間を検索。1000件を超えたら期間を半分に割って取り直す。"""
    p = dict(params)
    p["numericFilters"] = f"created_at_i>={lo},created_at_i<{hi}"
    p["hitsPerPage"] = PAGE
    r = http.get(BASE, params=p)
    if r is None or r.status_code != 200:
        log.warning("HN 取得失敗 %s-%s", lo, hi)
        return None
    try:
        js = r.json()
        if not isinstance(js.get("hits"), list) or "nbHits" not in js:
            return None
    except (ValueError, AttributeError):
        return None
    hits = js.get("hits", [])
    if js.get("nbHits", 0) > len(hits) and hi - lo > 600:
        mid = (lo + hi) // 2
        left = _search(params, lo, mid)
        right = _search(params, mid, hi)
        return None if left is None or right is None else left + right
    if js.get("nbHits", 0) > len(hits):
        return None  # 上限で欠けた集計を保存しない
    return hits


def fetch_day(day: date) -> list[dict]:
    lo, hi = day_bounds(day)
    hits = _search({"tags": "story",
                    "attributesToRetrieve": "title,author,created_at_i,points,url"}, lo, hi)
    if hits is None:
        raise RuntimeError("HN 取得失敗")
    docs = []
    for h in hits:
        title = (h.get("title") or "").strip()
        if not title:
            continue
        docs.append({
            "source": "hn",
            "id": f"hn:{h.get('objectID')}",
            "title": title,
            "url": h.get("url") or "",
            "voice": h.get("author") or "",
            "points": h.get("points") or 0,
        })
    return docs


def term_daily_counts(term: str, start: date, end: date) -> dict[str, dict] | None:
    """投稿とコメントの両方で、言葉がそのまま出てきた回数を日ごとに数える。"""
    lo, _ = day_bounds(start)
    _, hi = day_bounds(end)
    hits = _search({"query": f'"{term}"', "typoTolerance": "false", "advancedSyntax": "true",
                    "tags": "(story,comment)",
                    "attributesToRetrieve": "author,created_at_i"}, lo, hi)
    if hits is None:
        return None
    counts: dict[str, int] = defaultdict(int)
    voices: dict[str, set] = defaultdict(set)
    for h in hits:
        ts = h.get("created_at_i")
        if ts is None:
            continue
        d = ts_to_day(ts)
        counts[d] += 1
        voices[d].add(h.get("author"))
    return {d: {"count": counts[d], "voices": len(voices[d])} for d in counts}
