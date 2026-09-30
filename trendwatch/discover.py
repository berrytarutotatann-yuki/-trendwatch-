"""新語候補の発見。

点数の考え方（単純な「新しさ×伸び」の掛け算ではない）:
  expected = 過去の件数 × (最近の日数 / 過去の日数)   … 過去のペースなら最近何件のはずか
  z        = (最近の件数 − expected) / √(expected + 1) … 期待よりどれだけ多いか（ポアソンの z 値）
  score    = z × (1 + source_bonus × (出てきたデータ源の数 − 1))

・過去が0件でも無限大にならない
・件数が少ないうちは点数が控えめになる
・件数は「見出しの数」ではなく1見出し1回、さらに min_voices 人以上が使っていることを条件にする
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import store
from .config import Config
from .textproc import phrases
from .sources.media import unique_documents, fetch_day as media_day


def score_phrases(recent_docs: list[dict], base_docs: list[dict], recent_days: int,
                  base_days: int, min_count: int, min_voices: int, source_bonus: float) -> list[dict]:
    recent_docs = unique_documents(recent_docs)
    base_docs = unique_documents(base_docs)
    r_count: Counter = Counter()
    r_voices: dict[str, set] = defaultdict(set)
    r_sources: dict[str, set] = defaultdict(set)
    r_fields: dict[str, Counter] = defaultdict(Counter)
    r_examples: dict[str, list] = defaultdict(list)
    r_docs: dict[str, set] = defaultdict(set)
    for d in recent_docs:
        for p in phrases(d["title"]):
            r_count[p] += 1
            r_docs[p].add(d["id"])
            r_voices[p].add((d["source"], d.get("voice") or d["id"]))
            r_sources[p].add(d["source"])
            for f in d.get("fields") or []:
                r_fields[p][f] += 1
            if len(r_examples[p]) < 3:
                r_examples[p].append({"source": d["source"], "title": d["title"]})

    cands = {p for p, c in r_count.items() if c >= min_count and len(r_voices[p]) >= min_voices}
    b_count: Counter = Counter()
    for d in base_docs:
        for p in phrases(d["title"]):
            if p in cands:
                b_count[p] += 1

    rows = []
    for p in cands:
        recent = r_count[p]
        base = b_count[p]
        expected = base * recent_days / base_days if base_days > 0 else 0.0
        z = (recent - expected) / math.sqrt(expected + 1)
        n_src = len(r_sources[p])
        score = z * (1 + source_bonus * (n_src - 1))
        fields = r_fields[p]
        rows.append({
            "term": p,
            "score": round(score, 2),
            "z": round(z, 2),
            "recent": recent,
            "baseline": base,
            "expected": round(expected, 2),
            "voices": len(r_voices[p]),
            "sources": sorted(r_sources[p]),
            "field": fields.most_common(1)[0][0] if fields else "other",
            "is_new": base == 0,
            "examples": r_examples[p],
            "_docs": r_docs[p],
        })
    # 同点なら「途中に of/for などを含まない」「語数が多い（より具体的）」方を優先
    rows.sort(key=lambda r: (-r["score"], _has_mid_stop(r["term"]), -len(r["term"].split()), r["term"]))
    kept = dedupe(rows)
    for r in kept:
        r.pop("_docs", None)
    return kept


def _has_mid_stop(term: str) -> bool:
    return any(t in {"of", "and", "for", "to", "in", "on"} for t in term.split()[1:-1])


def dedupe(rows: list[dict], ratio: float = 0.7) -> list[dict]:
    """重なる候補は点数の高い方だけ残す。
    ・「system one」と「system one model」のように言葉が重なる
    ・ほぼ同じ見出しから出ている（同じ見出しの別の切り出し）"""
    kept: list[dict] = []
    for r in rows:
        toks = r["term"].split()
        clash = False
        for k in kept:
            kt = k["term"].split()
            same_docs = False
            if "_docs" in r and "_docs" in k:
                inter = len(r["_docs"] & k["_docs"])
                same_docs = inter / max(1, min(len(r["_docs"]), len(k["_docs"]))) >= 0.8
            if same_docs:  # 同じ見出しの別の切り出し → 件数に関係なく重複
                clash = True
                break
            if _contains(kt, toks) or _contains(toks, kt) or _overlap(kt, toks):
                small, big = sorted([r["recent"], k["recent"]])
                if big == 0 or small / big >= ratio:
                    clash = True
                    break
        if not clash:
            kept.append(r)
    return kept


def _contains(big: list[str], small: list[str]) -> bool:
    n = len(small)
    return n <= len(big) and any(big[i:i + n] == small for i in range(len(big) - n + 1))


def _overlap(a: list[str], b: list[str]) -> bool:
    """a の末尾と b の先頭（またはその逆）が2語以上重なる。"""
    for n in range(2, min(len(a), len(b))):
        if a[-n:] == b[:n] or b[-n:] == a[:n]:
            return True
    return False


def run_discovery(cfg: Config, day: date) -> dict:
    w, dc = cfg.windows, cfg.discovery
    recent_days = int(w.get("recent_days", 7))
    base_days_cfg = int(w.get("baseline_days", 90))
    recent_range = [day - timedelta(days=i) for i in range(recent_days)]
    base_range = [day - timedelta(days=recent_days + i) for i in range(base_days_cfg)]

    recent_docs = unique_documents([d for x in recent_range for d in [a for a in store.read_day(x) if a["source"] != "media"] + media_day(x)])
    base_available = [x for x in base_range if store.has_day(x)]
    base_docs = unique_documents([d for x in base_available for d in [a for a in store.read_day(x) if a["source"] != "media"] + media_day(x)])

    rows = score_phrases(recent_docs, base_docs, recent_days, len(base_available),
                         int(dc.get("min_count", 3)), int(dc.get("min_voices", 3)),
                         float(dc.get("source_bonus", 0.5)))

    excl = cfg.exclude_regexes()
    min_score = float(dc.get("min_score", 2.0))
    rows = [r for r in rows if r["score"] >= min_score and not any(rx.search(r["term"]) for rx in excl)]

    top_n = int(dc.get("top_n_per_field", 15))
    by_field: dict[str, list] = {}
    for key in list(cfg.fields) + ["other"]:
        lst = [r for r in rows if r["field"] == key][:top_n]
        for i, r in enumerate(lst):
            r["rank"] = i + 1
        by_field[key] = lst

    result = {
        "date": day.isoformat(),
        "recent_days": recent_days,
        "baseline_days_available": len(base_available),
        "baseline_days_wanted": base_days_cfg,
        "docs_recent": len(recent_docs),
        "docs_baseline": len(base_docs),
        "fields": by_field,
    }
    store.save_json(f"discovery/{day.isoformat()}.json", result)
    return result


def auto_track(cfg: Config, result: dict, today: date) -> list[str]:
    """上位の候補を自動でグラフ追跡に加え、期限切れの自動追加分を外す。"""
    dc = cfg.discovery
    per_field = int(dc.get("auto_track_per_field", 3))
    min_score = float(dc.get("auto_track_min_score", 4.0))
    expire = int(dc.get("auto_track_expire_days", 45))
    tracked = store.load_json("tracked.json", {})
    added = []
    for key, rows in result["fields"].items():
        if key == "other":
            continue
        for r in rows[:per_field]:
            if r["score"] >= min_score and r["term"] not in tracked:
                tracked[r["term"]] = {"field": key, "origin": "auto", "added": today.isoformat(),
                                      "score_at_add": r["score"]}
                added.append(r["term"])
    for term in list(tracked):
        t = tracked[term]
        if t.get("origin") == "auto" and not t.get("pinned"):
            if (today - date.fromisoformat(t["added"])).days > expire:
                del tracked[term]
    # 上限を超えたら、古い自動追加分から外す
    cap = int(dc.get("max_auto_tracked", 30))
    autos = sorted((t for t, v in tracked.items() if v.get("origin") == "auto" and not v.get("pinned")),
                   key=lambda t: (tracked[t]["added"], tracked[t].get("score_at_add", 0)))
    for term in autos[:max(0, len(autos) - cap)]:
        del tracked[term]
    store.save_json("tracked.json", tracked)
    return added
