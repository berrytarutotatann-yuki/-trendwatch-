"""API失敗・途中切れ・日付境界を、ネットに出ずに確認する。"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trendwatch import collect, store, track
from trendwatch.config import load_config
from trendwatch.sources import hn, arxiv, gdelt, qiita
from test_core import root


def response(data=None, text='', status=200):
    return SimpleNamespace(status_code=status, text=text, json=lambda: data)


@pytest.mark.parametrize('module', [hn, arxiv, gdelt, qiita])
def test_failure_is_not_zero(monkeypatch, module):
    monkeypatch.setattr(module.http, 'get', lambda *a, **kw: None)
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    assert module.term_daily_counts('slop ui', day, day) is None


def test_hn_phrase_and_partial_failure(monkeypatch):
    calls = []
    def get(url, params):
        calls.append(params)
        if len(calls) == 1:
            return response({'hits': [], 'nbHits': 1001})
        if len(calls) == 2:
            return response({'hits': [{'created_at_i': 1790553600, 'author': 'a'}], 'nbHits': 1})
        return None
    monkeypatch.setattr(hn.http, 'get', get)
    assert hn.term_daily_counts('slop ui', date(2026, 9, 28), date(2026, 9, 28)) is None
    assert calls[0]['advancedSyntax'] == 'true'
    assert calls[0]['typoTolerance'] == 'false'


def test_arxiv_error_feed(monkeypatch):
    monkeypatch.setattr(arxiv.http, 'get', lambda *a, **kw: response(text='<feed/>'))
    assert arxiv.term_daily_counts('term', date(2026, 9, 28), date(2026, 9, 28)) is None


def test_arxiv_partial_page(monkeypatch):
    monkeypatch.setattr(arxiv.http, 'get', lambda *a, **kw: response())
    pages = iter([(1001, [{'title': 'one'}]), (1001, [])])
    monkeypatch.setattr(arxiv, 'parse_feed', lambda t: next(pages))
    assert arxiv._query_all('term') is None


def test_gdelt_text_error(monkeypatch):
    monkeypatch.setattr(gdelt.http, 'get', lambda *a, **kw: response(text='Please try again'))
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    assert gdelt.term_daily_counts('term', day, day) is None


def test_qiita_utc_and_query(monkeypatch):
    def get(url, params, headers):
        assert 'created:>=2026-09-27' in params['query']
        assert 'created:<2026-09-30' in params['query']
        return response([{'created_at': t, 'user': {'id': 'u'}} for t in
                         ['2026-09-28T08:59:59+09:00', '2026-09-29T08:59:59+09:00',
                          '2026-09-29T09:00:00+09:00']])
    monkeypatch.setattr(qiita.http, 'get', get)
    assert qiita.term_daily_counts('Python', date(2026, 9, 28), date(2026, 9, 28)) == {
        '2026-09-28': {'count': 1, 'voices': 1}}


def test_qiita_partial_failure(monkeypatch):
    full = [{'created_at': '2026-09-28T00:00:00Z', 'user': {'id': 'u'}}] * 100
    replies = iter([response(full), None])
    monkeypatch.setattr(qiita.http, 'get', lambda *a, **kw: next(replies))
    assert qiita.term_daily_counts('Python', date(2026, 9, 28), date(2026, 9, 28)) is None


def test_collection_continues_and_preserves_failed_source(root, monkeypatch):
    cfg = load_config()
    day = date(2026, 9, 28)
    old = {'id': 'arxiv:old', 'source': 'arxiv', 'title': 'old paper', 'fields': ['ai']}
    store.write_day(day, [old])
    monkeypatch.setattr(hn, 'fetch_day', lambda d: [{'id': 'hn:new', 'source': 'hn', 'title': 'AI agent'}])
    def fail(*args):
        raise ValueError('bad response')
    monkeypatch.setattr(arxiv, 'fetch_day', fail)
    assert collect.collect_day(cfg, day, sources=('hn', 'arxiv')) == 2
    assert {d['id'] for d in store.read_day(day)} == {'arxiv:old', 'hn:new'}


def test_failed_tracking_keeps_old_data(root, monkeypatch):
    cfg = load_config()
    old = {'days': {'2026-09-27': {'count': 3, 'voices': 2}},
           'fetched_from': '2026-06-01', 'fetched_to': '2026-09-27'}
    store.save_json('series.json', {'slop ui': {'hn': old}})
    monkeypatch.setattr(track, 'SOURCES', {'hn': lambda *a: None})
    result = track.update_series(cfg, date(2026, 9, 28), only=['slop ui'])
    assert result['slop ui']['hn'] == old


def test_http_interval_after_slow_response(monkeypatch):
    from trendwatch import http
    clock = [100.0]
    sleeps = []
    monkeypatch.setattr(http.time, 'monotonic', lambda: clock[0])
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    def get(*a, **kw):
        clock[0] += 20  # 応答に20秒かかっても、その後5.5秒待つ
        return response()
    monkeypatch.setattr(http.time, 'sleep', sleep)
    monkeypatch.setattr(http, '_last_call', {})
    monkeypatch.setattr(http._session, 'get', get)
    http.get(gdelt.BASE)
    http.get(gdelt.BASE)
    assert sleeps == [http.MIN_INTERVAL['api.gdeltproject.org']]
