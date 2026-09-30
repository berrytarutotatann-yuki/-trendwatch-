"""見出しから2〜3語のフレーズを取り出す。"""
from __future__ import annotations

import re

STOPWORDS = set("""
a an the and or but nor of for to in on at by with from into onto over under about after before
between through during without within via vs versus as is are was were be been being am do does
did done has have had having can could will would shall should may might must not no yes
i me my we us our you your he him his she her it its they them their this that these those
there here what which who whom whose when where why how all any both each few more most other
some such only own same so than too very just also now then once again ever still even new
using use used based towards toward toward s t re ve ll d m y o up down out off if else
let lets let's get gets got make makes made one's i'm it's don't can't won't isn't aren't
hn show ask tell launch part episode review update updates introducing announcing
""".split())

# 先頭・末尾に来てはいけないが、途中なら許す語（例: "system one model" の one は OK）
EDGE_ONLY = STOPWORDS | {"one", "two", "three", "first", "last", "next", "best", "top",
                          "big", "small", "good", "bad", "really", "like", "way", "ways",
                          "thing", "things", "year", "years", "day", "days", "time",
                          "people", "world", "free", "open", "why", "via"}

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#\-']*[a-z0-9+#]|[a-z0-9]")


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    toks = TOKEN_RE.findall(text)
    out = []
    for t in toks:
        if t.endswith("'s"):
            t = t[:-2]
        out.append(t)
    return out


def _ok_token(t: str) -> bool:
    if not t:
        return False
    if t.replace(".", "").replace(",", "").isdigit():
        return False
    if len(t) == 1 and not t.isalpha():
        return False
    return True


def phrases(text: str, n_min: int = 2, n_max: int = 3) -> set[str]:
    """見出し1件から、重複なしのフレーズ集合を返す。"""
    toks = tokenize(text)
    out: set[str] = set()
    for n in range(n_min, n_max + 1):
        for i in range(len(toks) - n + 1):
            gram = toks[i:i + n]
            if not all(_ok_token(t) for t in gram):
                continue
            if gram[0] in EDGE_ONLY or gram[-1] in EDGE_ONLY:
                continue
            if any(t in STOPWORDS and t not in {"of", "and", "for", "to", "in", "on"} for t in gram[1:-1]):
                continue
            if not any(any(c.isalpha() for c in t) and len(t) >= 3 for t in gram):
                continue
            out.add(" ".join(gram))
    return out

