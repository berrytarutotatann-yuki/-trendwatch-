"""GDELT（世界中のニュース記事の公開 API、登録不要。5秒に1回まで、過去約3か月分）。"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .. import http

log = logging.getLogger(__name__)
BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_LOOKBACK_DAYS = 88


def _json(r):
    if r is None or r.status_code != 200:
        return None
    try:
        return json.loads(r.text)
    except ValueError:
        # 混雑時は JSON ではなく文章でエラーが返る
        log.warning("GDELT: JSON でない応答: %s", r.text[:120])
        return None


def fetch_day(day: date, query: str, field_key: str, chunks: int = 4) -> list[dict]:
    """1日を chunks 個に区切って、英語ニュースの見出しを集める（1回250件まで）。"""
    if (datetime.now(timezone.utc).date() - day).days > MAX_LOOKBACK_DAYS:
        return []
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    step = timedelta(hours=24 / chunks)
    docs = []
    for i in range(chunks):
        a, b = start + step * i, start + step * (i + 1) - timedelta(seconds=1)
        js = _json(http.get(BASE, params={
            "query": f"{query} sourcelang:english", "mode": "artlist", "format": "json",
            "maxrecords": 250, "sort": "DateDesc",
            "startdatetime": a.strftime("%Y%m%d%H%M%S"),
            "enddatetime": b.strftime("%Y%m%d%H%M%S")}))
        if js is None:
            raise RuntimeError("GDELT 見出し取得失敗")
        for art in (js or {}).get("articles", []) or []:
            title = (art.get("title") or "").strip()
            if not title:
                continue
            docs.append({"source": "news", "id": "news:" + (art.get("url") or title),
                         "title": title, "url": art.get("url") or "", "voice": art.get("domain") or "",
                         "fields": [field_key]})
    return docs


def parse_timeline(js: dict) -> dict[str, dict]:
    counts: dict[str, int] = defaultdict(int)
    for series in (js or {}).get("timeline", []) or []:
        for pt in series.get("data", []) or []:
            raw = str(pt.get("date", ""))
            d = raw[:8]
            if len(d) == 8 and d.isdigit():
                counts[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] += int(pt.get("value") or 0)
        break  # 最初の系列（記事数）だけ使う
    return {d: {"count": c, "voices": None} for d, c in counts.items()}


def term_daily_counts(term: str, start: date, end: date) -> dict[str, dict] | None:
    earliest = datetime.now(timezone.utc).date() - timedelta(days=MAX_LOOKBACK_DAYS)
    start = max(start, earliest)
    if start > end:
        return {}
    js = _json(http.get(BASE, params={
        "query": f'"{term}"', "mode": "timelinevolraw", "format": "json",
        "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959"}))
    if js is None or not isinstance(js, dict) or "timeline" not in js:
        return None
    out = parse_timeline(js)
    # データが返ってきた日は0件の日も0として埋める（「取れなかった」と区別するため）
    d = start
    while d <= end:
        out.setdefault(d.isoformat(), {"count": 0, "voices": None})
        d += timedelta(days=1)
    return out
