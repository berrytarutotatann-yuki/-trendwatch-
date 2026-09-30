from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from trendwatch import store, track
from trendwatch.config import load_config
from trendwatch.dashboard import build
from trendwatch.discover import run_discovery
from trendwatch.sources import media
from test_core import root

NOW = datetime(2026, 9, 29, 14, tzinfo=timezone.utc)


def rss(title='AI agents power chips', day='Mon, 28 Sep 2026 12:00:00 GMT', url='https://example.com/one', extra=''):
    return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{day}</pubDate>{extra}</item></channel></rss>'.encode()


def config():
    cfg = load_config()
    cfg.raw['media'] = {'publishers': {'one': {'label':'One', 'site':'https://example.com', 'feed':'https://example.com/feed'}}}
    return cfg


def test_rss_utc_and_url():
    got, bad = media.parse_feed(rss(day='Tue, 29 Sep 2026 08:00:00 +0900', url='https://www.example.com/a?utm_source=x&amp;id=7#top'), 'one', {})
    assert bad == 0
    assert got[0]['date'] == '2026-09-28'
    assert got[0]['url'] == 'https://example.com/a?id=7'
    assert 'description' not in got[0]


def test_atom_published_not_updated():
    xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <title type="html">AI &amp;amp; chips</title><link href="https://example.com/a"/>
    <published>2026-09-27T21:00:00-04:00</published><updated>2026-09-29T10:00:00Z</updated>
    </entry></feed>'''
    got, bad = media.parse_feed(xml, 'one', {})
    assert got[0]['date'] == '2026-09-28'
    assert got[0]['title'] == 'AI & chips'
    assert bad == 0


def test_invalid_date_and_unsafe_link_are_not_articles():
    assert media.parse_feed(rss(day='invalid'), 'one', {}) == ([], 1)
    assert media.parse_feed(rss(url='javascript:alert(1)'), 'one', {}) == ([], 1)
    with pytest.raises(ValueError):
        media.parse_feed('<html/>', 'one', {})


def test_reuters_search_accepts_only_matching_publisher():
    spec = {'method':'search', 'domain':'reuters.com'}
    got, _ = media.parse_feed(rss(title='AI agents - Reuters', extra='<source url="https://www.reuters.com">Reuters</source>'), 'reuters', spec)
    assert got[0]['title'] == 'AI agents'
    assert media.parse_feed(rss(extra='<source url="https://other.com">Reuters</source>'), 'reuters', spec) == ([], 1)


def test_refresh_merges_and_failure_keeps_old_data(root, monkeypatch):
    cfg = config()
    monkeypatch.setattr(media.http, 'get', lambda *a, **kw: SimpleNamespace(status_code=200, content=rss()))
    first = media.refresh(cfg, force=True, now=NOW)
    again = media.refresh(cfg, force=True, now=NOW)
    assert len(again['articles']) == 1
    assert first['articles'] == again['articles']
    monkeypatch.setattr(media.http, 'get', lambda *a, **kw: SimpleNamespace(status_code=403))
    failed = media.refresh(cfg, force=True, now=NOW)
    assert failed['articles'] == first['articles']
    assert failed['publishers']['one']['status'] == 'error'
    assert failed['publishers']['one']['last_success'] == NOW.isoformat()
    # 媒体だけの履歴で、HN/arXivも収集済みとは扱わない。
    assert not store.has_day(date(2026,9,28))


def test_coverage_unknown_partial_and_zero(root, monkeypatch):
    cfg = config()
    monkeypatch.setattr(media.http, 'get', lambda *a, **kw: SimpleNamespace(status_code=200, content=rss(day='Sun, 27 Sep 2026 12:00:00 GMT')))
    media.refresh(cfg, force=True, now=NOW)
    result = media.term_daily_counts('AI agents', date(2026,9,26), date(2026,9,29))
    assert result['2026-09-26']['count'] is None
    assert result['2026-09-27']['count'] == 1
    assert result['2026-09-27']['partial']
    assert result['2026-09-28']['count'] == 0
    assert not result['2026-09-28']['partial']
    assert result['2026-09-29']['partial']


def test_search_coverage_never_claims_complete(root, monkeypatch):
    cfg = config()
    cfg.raw['media']['publishers']['one'].update(method='search', domain='reuters.com')
    monkeypatch.setattr(media.http, 'get', lambda *a, **kw: SimpleNamespace(status_code=200, content=rss(day='Sun, 27 Sep 2026 12:00:00 GMT', extra='<source url="https://reuters.com">Reuters</source>')))
    cache = media.refresh(cfg, force=True, now=NOW)
    assert set(cache['publishers']['one']['coverage'].values()) == {'partial'}


def test_one_failed_feed_does_not_stop_others(root, monkeypatch):
    cfg = config()
    cfg.raw['media']['publishers']['two'] = {'label':'Two','feed':'https://two.com/feed','site':'https://two.com'}
    def get(url, **kw):
        if 'example' in url:
            raise RuntimeError('network')
        return SimpleNamespace(status_code=200, content=rss(url='https://two.com/a'))
    monkeypatch.setattr(media.http, 'get', get)
    cache = media.refresh(cfg, force=True, now=NOW)
    assert cache['publishers']['one']['status'] == 'error'
    assert cache['publishers']['two']['status'] == 'ok'
    assert len(cache['articles']) == 1


def test_caching_avoids_repeated_requests_for_backfill(root, monkeypatch):
    cfg = config()
    calls = []
    def get(*a, **kw):
        calls.append(a)
        return SimpleNamespace(status_code=200, content=rss())
    monkeypatch.setattr(media.http, 'get', get)
    media.refresh(cfg, now=NOW)
    media.refresh(cfg, now=NOW)
    assert len(calls) == 1


def test_dedupe_across_sources_preserves_distinct_articles():
    docs = [
        {'id':'hn:1','source':'hn','title':'AI agents','url':'https://example.com/a?utm_medium=rss'},
        {'id':'media:1','source':'media','title':'AI agents','url':'https://example.com/a'},
        {'id':'news:1','source':'news','title':'AI agents'},
        {'id':'media:2','source':'media','title':'AI agents','url':'https://other.com/b'},
    ]
    assert {d['id'] for d in media.unique_documents(docs)} == {'media:1', 'media:2'}


@pytest.mark.parametrize('term,title,expected', [('ai', 'chair', False), ('ai agents','AI-agents rise',True), ('AI','OpenAI',False), ('HBM4','HBM4 chips',True)])
def test_whole_phrase_matching(term,title,expected):
    assert media.matches(term,title) is expected


def test_media_archive_enters_discovery_and_dashboard(root, monkeypatch):
    cfg = config()
    cfg.raw['media']['publishers'] = {k:{'label':k,'feed':f'https://{k}.com/feed','site':f'https://{k}.com'} for k in ('one','two','three')}
    def get(url, **kw):
        return SimpleNamespace(status_code=200, content=rss(url=url.replace('/feed','/a')))
    monkeypatch.setattr(media.http, 'get', get)
    media.refresh(cfg, now=NOW)
    result = run_discovery(cfg, date(2026,9,28))
    assert result['docs_recent'] == 3
    assert result['fields']['ai']
    assert result['baseline_days_available'] == 0
    track.update_series(cfg, date(2026,9,28), sources={'media':media.term_daily_counts})
    from trendwatch.dashboard import _pack
    series = store.load_json('series.json', {})['slop ui']['media']
    packed = _pack('media', series)
    assert packed['c']['2026-09-01'] is None
    out = build(cfg, root/'index.html')
    html = out.read_text()
    assert 'mediaHeat' in html and 'メディアへの広がり' in html
    assert 'mediaStatus' in html


def test_same_publisher_title_is_not_counted_twice(root, monkeypatch):
    cfg = config()
    xml = rss().replace(b'</channel>', rss(url='https://example.com/alternate').split(b'<channel>')[1].split(b'</channel>')[0] + b'</channel>')
    monkeypatch.setattr(media.http, 'get', lambda *a, **kw: SimpleNamespace(status_code=200, content=xml))
    cache = media.refresh(cfg, force=True, now=NOW)
    assert len(cache['articles']) == 1


def test_future_articles_do_not_enter_archive(root, monkeypatch):
    cfg = config()
    monkeypatch.setattr(media.http, 'get', lambda *a, **kw: SimpleNamespace(status_code=200, content=rss(day='Wed, 30 Sep 2026 12:00:00 GMT')))
    cache = media.refresh(cfg, force=True, now=NOW)
    assert cache['publishers']['one']['status'] == 'error'
    assert cache['articles'] == {}
