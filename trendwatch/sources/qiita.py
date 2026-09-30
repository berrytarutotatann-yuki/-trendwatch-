"""Qiita（日本語の技術記事）。日本語圏でもう使われ始めたかを見る。

登録なしでも1時間60回まで使える。環境変数 QIITA_TOKEN を入れると1時間1000回まで。
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .. import http

log = logging.getLogger(__name__)
BASE = "https://qiita.com/api/v2/items"


def term_daily_counts(term: str, start: date, end: date, max_pages: int = 5) -> dict[str, dict] | None:
    headers = {}
    token = os.environ.get("QIITA_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # 検索側の時差を吸収し、返された時刻をUTCで絞り直す。
    q = f'"{term}" created:>={(start - timedelta(days=1)).isoformat()} created:<{(end + timedelta(days=2)).isoformat()}'
    counts: dict[str, int] = defaultdict(int)
    voices: dict[str, set] = defaultdict(set)
    for page in range(1, max_pages + 1):
        r = http.get(BASE, params={"query": q, "per_page": 100, "page": page}, headers=headers)
        if r is None or r.status_code != 200:
            if r is not None and r.status_code == 403:
                log.warning("Qiita: 回数制限に達しました（QIITA_TOKEN を設定すると増えます）")
            return None
        try:
            items = r.json()
        except ValueError:
            return None
        if not isinstance(items, list):
            return None
        for it in items:
            ts = it.get("created_at")
            if not ts:
                continue
            d = datetime.fromisoformat(ts).astimezone(timezone.utc).date().isoformat()
            if not start.isoformat() <= d <= end.isoformat():
                continue
            counts[d] += 1
            voices[d].add((it.get("user") or {}).get("id"))
        if len(items) < 100:
            return _pack(counts, voices)
    log.warning("Qiita: ページ上限に達したため集計を保存しません")
    return None


def _pack(counts, voices):
    return {d: {"count": counts[d], "voices": len(voices[d])} for d in counts}
