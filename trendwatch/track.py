"""追跡中の言葉について、データ源ごとの日ごとの言及数を集める（グラフ用）。

初回は series_days 日分をまとめて取り、2回目以降は直近14日分だけ取り直して上書きする
（投稿やコメントは後から増えるので、少し前まで取り直す）。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from . import store
from .config import Config
from .sources import arxiv, gdelt, hn, qiita, media

log = logging.getLogger(__name__)
REFRESH_DAYS = 14

SOURCES = {
    "hn": hn.term_daily_counts,
    "arxiv": arxiv.term_daily_counts,
    "news": gdelt.term_daily_counts,
    "qiita": qiita.term_daily_counts,
    "media": media.term_daily_counts,
}


def tracked_terms(cfg: Config) -> dict[str, dict]:
    tracked = dict(store.load_json("tracked.json", {}))
    for t in cfg.tracked_terms:
        term = str(t["term"]).strip()
        prev = tracked.get(term, {})
        tracked[term] = {**prev, "field": t.get("field", prev.get("field", "other")),
                         "origin": "config", "tickers": list(t.get("tickers") or [])}
    return tracked


def update_series(cfg: Config, today: date, only: list[str] | None = None,
                  sources: dict | None = None) -> dict:
    series_days = int(cfg.windows.get("series_days", 120))
    first = today - timedelta(days=series_days - 1)
    series = store.load_json("series.json", {})
    terms = tracked_terms(cfg)
    for term in terms:
        if only and term not in only:
            continue
        cur = series.setdefault(term, {})
        for src, fn in (SOURCES if sources is None else sources).items():
            s = cur.setdefault(src, {"days": {}, "fetched_from": None})
            if s["fetched_from"] and s["fetched_from"] <= first.isoformat() and s["days"]:
                start = today - timedelta(days=REFRESH_DAYS)
                if s.get("fetched_to"):
                    start = max(first, min(start, date.fromisoformat(s["fetched_to"]) + timedelta(days=1)))
            else:
                start = first
            try:
                got = fn(term, start, today)
            except Exception as e:  # 1つの失敗で全体を止めない
                log.warning("%s / %s 取得エラー: %s", term, src, e)
                got = None
            if got is None:
                log.warning("%s / %s: 取得失敗。前回のデータを保持します", term, src)
                continue
            log.info("%s / %s: %d件", term, src, sum(v["count"] or 0 for v in got.values()))
            # 取り直した期間は一度消してから入れる（0件の日を正しく0にするため）
            s["days"] = {d: v for d, v in s["days"].items() if d < start.isoformat()}
            s["days"].update(got)
            s["days"] = {d: v for d, v in s["days"].items() if d >= first.isoformat()}
            if not s["fetched_from"] or start == first:
                s["fetched_from"] = start.isoformat()
            s["fetched_to"] = today.isoformat()
        log.info("追跡更新: %s", term)
    # 追跡から外れた言葉のデータは消す
    for term in list(series):
        if term not in terms:
            del series[term]
    store.save_json("series.json", series)
    return series
