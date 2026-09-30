import json
from datetime import date, timedelta

import pytest

from trendwatch import store
from trendwatch.config import load_config
from trendwatch.discover import auto_track, dedupe, run_discovery, score_phrases
from trendwatch.sources import arxiv, gdelt
from trendwatch.textproc import phrases


@pytest.fixture
def root(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent
    shutil.copy(src / "config.yaml", tmp_path / "config.yaml")
    monkeypatch.setattr("trendwatch.config.ROOT", tmp_path)
    return tmp_path


def test_phrases_basic():
    p = phrases("Introducing System One Models and Jev")
    assert "system one models" in p
    assert "one models" not in p          # 先頭が one
    assert not any(x.startswith("introducing") for x in p)


def test_phrases_hyphen_and_numbers():
    p = phrases("On-policy distillation beats RLHF in 2026")
    assert "on-policy distillation" in p
    assert not any("2026" in x for x in p)


def _doc(i, title, source="hn", voice=None, fields=("ai",)):
    return {"source": source, "id": f"{source}:{i}", "title": title,
            "voice": voice or f"user{i}", "fields": list(fields)}


def test_score_new_term_beats_common_term():
    recent = [_doc(i, "synthetic memory for agents") for i in range(5)]
    recent += [_doc(100 + i, "machine learning news") for i in range(8)]
    base = [_doc(200 + i, "machine learning news") for i in range(100)]
    rows = score_phrases(recent, base, 7, 90, 3, 3, 0.5)
    terms = [r["term"] for r in rows]
    assert terms[0] == "synthetic memory"
    ml = next(r for r in rows if r["term"].startswith("machine learning") or r["term"] == "learning news")
    assert ml["score"] < rows[0]["score"]


def test_single_author_spam_is_filtered():
    recent = [_doc(i, "quantum soup protocol", voice="spammer") for i in range(10)]
    rows = score_phrases(recent, [], 7, 90, 3, 3, 0.5)
    assert rows == []


def test_multi_source_bonus():
    a = [_doc(i, "glass substrate boom", source="hn") for i in range(4)]
    b = [_doc(i, "glass substrate boom", source="hn") for i in range(2)] + \
        [_doc(10 + i, "glass substrate boom", source="news") for i in range(2)]
    ra = score_phrases(a, [], 7, 90, 3, 3, 0.5)[0]
    rb = score_phrases(b, [], 7, 90, 3, 3, 0.5)[0]
    assert rb["score"] > ra["score"]


def test_zero_baseline_is_finite():
    recent = [_doc(i, "slop ui tells") for i in range(4)]
    r = score_phrases(recent, [], 7, 0, 3, 3, 0.5)
    assert all(abs(x["score"]) < 100 for x in r)


def test_dedupe_prefers_first():
    rows = [{"term": "system one model", "recent": 10}, {"term": "system one", "recent": 10},
            {"term": "one model family", "recent": 9}, {"term": "slop ui", "recent": 5}]
    kept = [r["term"] for r in dedupe(rows)]
    assert kept == ["system one model", "slop ui"]


def test_arxiv_parse():
    xml = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry><id>http://arxiv.org/abs/2609.01234v1</id><published>2026-09-27T10:00:00Z</published>
    <title>Mutable Transcripts:
      Editable Conversation State</title>
    <author><name>A. Author</name></author><author><name>B. Author</name></author>
    <category term="cs.AI"/><category term="cs.CL"/></entry>
</feed>"""
    total, entries = arxiv.parse_feed(xml)
    assert total == 1
    e = entries[0]
    assert e["title"] == "Mutable Transcripts: Editable Conversation State"
    assert e["first_author"] == "A. Author"
    assert e["categories"] == ["cs.AI", "cs.CL"]
    assert e["published"] == "2026-09-27"


def test_gdelt_timeline_aggregates_by_day():
    js = {"timeline": [{"series": "Article Count", "data": [
        {"date": "20260920T000000Z", "value": 3}, {"date": "20260920T120000Z", "value": 2},
        {"date": "20260921T000000Z", "value": 7}]}]}
    out = gdelt.parse_timeline(js)
    assert out["2026-09-20"]["count"] == 5
    assert out["2026-09-21"]["count"] == 7


def test_end_to_end_offline(root, monkeypatch):
    cfg = load_config(root / "config.yaml")
    day = date(2026, 9, 27)
    # 過去: よくある言葉だけ / 最近: 新しい言葉が複数の場所に出る
    for i in range(1, 60):
        d = day - timedelta(days=i + 6)
        store.write_day(d, [_doc(f"{d}-{j}", "rust compiler release notes", voice=f"u{j}") for j in range(3)])
    for i in range(7):
        d = day - timedelta(days=i)
        store.write_day(d, [
            _doc(f"{d}-a", "Tells of a slop ui in the wild", voice=f"a{i}"),
            _doc(f"{d}-n", "Why every startup ships a slop ui now", source="news", voice=f"site{i}.com"),
            _doc(f"{d}-r", "rust compiler release notes", voice=f"r{i}"),
        ])
    res = run_discovery(cfg, day)
    ai = res["fields"]["ai"]
    assert ai and ai[0]["term"] == "slop ui"
    assert res["baseline_days_available"] == 59
    added = auto_track(cfg, res, day)
    assert "slop ui" in added

    # グラフ用データ（ネットに出ないよう差し替え）
    from trendwatch import track
    fake = {d.isoformat(): {"count": 2, "voices": 2} for d in [day - timedelta(days=k) for k in range(10)]}
    monkeypatch.setattr(track, "SOURCES", {"hn": lambda *a: fake, "arxiv": lambda *a: {},
                                            "news": lambda *a: None, "qiita": lambda *a: {}})
    series = track.update_series(cfg, day)
    assert series["slop ui"]["hn"]["days"]
    assert "news" in series["slop ui"] and not series["slop ui"]["news"]["days"]

    from trendwatch.dashboard import build
    out = build(cfg, root / "index.html")
    html = out.read_text(encoding="utf-8")
    assert "slop ui" in html and "/*__DATA__*/null" not in html
    payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    data = json.loads(payload.replace("<\\/", "</"))
    assert data["series"]["slop ui"]["hn"]["from"]
    assert data["series"]["slop ui"]["hn"]["to"] == day.isoformat()
    assert "<th>.com</th>" not in html and "Verisign" not in html
    assert "news" not in data["series"]["slop ui"]  # 取得失敗は「データなし」
