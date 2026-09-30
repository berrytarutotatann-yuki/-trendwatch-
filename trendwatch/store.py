"""データの保存と読み込み。

data/docs/YYYY-MM-DD.jsonl.gz  … その日に集めた見出し（1行1件）
data/tracked.json              … グラフで追跡している言葉
data/series.json               … 追跡語の日ごとの言及数
data/prices.json               … 株価（任意）
data/discovery/YYYY-MM-DD.json … その日の新語候補
"""
from __future__ import annotations

import gzip
import json
from datetime import date, timedelta
from pathlib import Path

from .config import data_dir


def docs_path(day: date) -> Path:
    d = data_dir() / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{day.isoformat()}.jsonl.gz"


def has_day(day: date) -> bool:
    return docs_path(day).exists()


def write_day(day: date, docs: list[dict]) -> None:
    p = docs_path(day)
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    tmp.replace(p)


def read_day(day: date) -> list[dict]:
    p = docs_path(day)
    if not p.exists():
        return []
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stored_days() -> list[date]:
    d = data_dir() / "docs"
    if not d.exists():
        return []
    out = []
    for p in d.glob("*.jsonl.gz"):
        try:
            out.append(date.fromisoformat(p.name[:10]))
        except ValueError:
            pass
    return sorted(out)


def prune_docs(keep_days: int, today: date) -> int:
    cutoff = today - timedelta(days=keep_days)
    n = 0
    for day in stored_days():
        if day < cutoff:
            docs_path(day).unlink()
            n += 1
    return n


def load_json(name: str, default):
    p = data_dir() / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(name: str, obj) -> None:
    p = data_dir() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def latest_discovery() -> tuple[str | None, dict | None]:
    d = data_dir() / "discovery"
    if not d.exists():
        return None, None
    files = sorted(d.glob("*.json"))
    if not files:
        return None, None
    p = files[-1]
    return p.stem, json.loads(p.read_text(encoding="utf-8"))
