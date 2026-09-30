"""1日分の見出しを全データ源から集めて保存する。"""
from __future__ import annotations

import logging
from datetime import date

from . import store
from .config import Config
from .sources import arxiv, gdelt, hn, media

log = logging.getLogger(__name__)


def collect_day(cfg: Config, day: date, sources: tuple[str, ...] = ("hn", "arxiv", "news", "media")) -> int:
    docs: list[dict] = []
    failed = set()

    def fetch(source, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:
            failed.add(source)
            log.warning("%s %s 取得失敗: %s", day, source, exc)
            return []

    if "media" in sources:
        fetch("media", media.refresh, cfg)
        docs += fetch("media", media.fetch_day, day)
    if "hn" in sources:
        got = fetch("hn", hn.fetch_day, day)
        log.info("%s HN: %d件", day, len(got))
        docs += got
    if "arxiv" in sources:
        cats = sorted({c for f in cfg.fields.values() for c in f.arxiv_categories})
        got = fetch("arxiv", arxiv.fetch_day, day, cats)
        log.info("%s arXiv: %d件", day, len(got))
        docs += got
    if "news" in sources:
        for f in cfg.fields.values():
            if f.news_query:
                got = fetch("news", gdelt.fetch_day, day, f.news_query, f.key)
                log.info("%s ニュース(%s): %d件", day, f.label, len(got))
                docs += got

    # 再取得に失敗したデータ源の以前の見出しは残す。
    docs += [d for d in store.read_day(day) if d["source"] in failed or d["source"] not in sources]
    if not docs and failed:
        return 0

    # 分野の振り分け＋重複除去
    seen: dict[str, dict] = {}
    for d in docs:
        fields = set(d.get("fields") or [])
        if d["source"] == "arxiv":
            fields |= set(cfg.fields_for_arxiv(d.get("categories") or []))
        fields |= set(cfg.fields_for_text(d["title"]))
        d["fields"] = sorted(fields)
        d.pop("categories", None)
        if d["id"] in seen:
            seen[d["id"]]["fields"] = sorted(set(seen[d["id"]]["fields"]) | fields)
        else:
            seen[d["id"]] = d
    out = list(seen.values())
    store.write_day(day, out)
    return len(out)
