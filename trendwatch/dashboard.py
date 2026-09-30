"""docs/index.html（グラフのページ）を作る。データはページの中に埋め込むので、1ファイルで完結する。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .config import Config, docs_dir
from .track import tracked_terms
from .media_dashboard import pack_media

TEMPLATE = Path(__file__).with_name("template.html")


def _pack(src: str, s: dict) -> dict:
    """グラフ用に {from: 集計開始日, c: {日付: 件数}} へ。from より前は「データなし」、以降で記録のない日は0件。"""
    days = s.get("days", {})
    start = s["fetched_from"]
    if src == "news" and days:  # GDELT は約3か月前までしか無いので、実際に返ってきた最初の日から
        start = max(start, min(days))
    if src == "media":
        return {"from": start, "to": s.get("fetched_to"),
                "c": {d: v["count"] for d, v in days.items()},
                "partial": [d for d, v in days.items() if v.get("partial")]}
    return {"from": start, "to": s.get("fetched_to"),
            "c": {d: v["count"] for d, v in days.items() if v.get("count")}}


def build(cfg: Config, out: Path | None = None) -> Path:
    disc_date, disc = store.latest_discovery()
    series = store.load_json("series.json", {})
    prices = store.load_json("prices.json", {})
    terms = tracked_terms(cfg)
    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "fields": {k: f.label for k, f in cfg.fields.items()},
        "discovery": disc,
        "tracked": [{"term": t, **{k: v for k, v in meta.items() if k in
                                   ("field", "origin", "added", "tickers", "pinned")}}
                    for t, meta in terms.items()],
        "series": {t: {src: _pack(src, s) for src, s in srcs.items() if s.get("fetched_from")}
                   for t, srcs in series.items()},
        "prices": prices,
        "media": pack_media(cfg, terms, disc),
        "series_days": int(cfg.windows.get("series_days", 120)),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
    out = out or docs_dir() / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
