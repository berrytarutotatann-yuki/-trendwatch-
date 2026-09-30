"""指定媒体の公開RSS/Atomを保存。収集前の日・失敗した日は0件にしない。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from .. import http, store

log = logging.getLogger(__name__)
ATOM = '{http://www.w3.org/2005/Atom}'
DC = '{http://purl.org/dc/elements/1.1/}'


def canonical_url(url: str) -> str:
    """追跡用パラメータだけ除き、記事を区別するパラメータは残す。"""
    try:
        p = urlsplit(url.strip())
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            return ''
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in ('mod', 'oc', 'ref', 'fbclid', 'gclid')]
        host = p.netloc.lower().removeprefix('www.')
        return urlunsplit(('https', host, p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))
    except ValueError:
        return ''


def title_key(title: str) -> str:
    return re.sub(r'[^\w]+', ' ', unescape(title).casefold()).strip()


def matches(term: str, title: str) -> bool:
    needle, haystack = title_key(term), title_key(title)
    return bool(needle) and f' {needle} ' in f' {haystack} '


def parse_feed(content: bytes | str, publisher: str, spec: dict) -> tuple[list[dict], int]:
    root = ET.fromstring(content)
    if root.tag == 'rss' and root.find('channel') is not None:
        items, atom = root.findall('./channel/item'), False
    elif root.tag == ATOM + 'feed':
        items, atom = root.findall(ATOM + 'entry'), True
    else:
        raise ValueError('RSS / Atom形式ではありません')
    articles, invalid = {}, 0
    for item in items:
        try:
            prefix = ATOM if atom else ''
            title = unescape(item.findtext(prefix + 'title') or '')
            title = re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', title)).strip()
            if atom:
                link = next((x.get('href', '') for x in item.findall(ATOM + 'link')
                             if x.get('rel', 'alternate') == 'alternate'), '')
                raw_date = item.findtext(ATOM + 'published') or item.findtext(ATOM + 'updated')
            else:
                link = item.findtext('link') or ''
                raw_date = item.findtext('pubDate') or item.findtext(DC + 'date')
            if spec.get('method') == 'search':
                src = item.find('source')
                source_host = urlsplit(src.get('url', '') if src is not None else '').hostname or ''
                domain = spec.get('domain', '')
                if not domain or not (source_host == domain or source_host.endswith('.' + domain)):
                    invalid += 1
                    continue
                title = re.sub(r'\s+-\s+(?:Reuters|reuters\.com)$', '', title, flags=re.I)
            if not raw_date:
                raise ValueError('公開日なし')
            try:
                published = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            except ValueError:
                published = parsedate_to_datetime(raw_date)
            if published.tzinfo is None:
                raise ValueError('タイムゾーンなし')
            published = published.astimezone(timezone.utc)
            url = canonical_url(link)
            if not title or not url:
                raise ValueError('見出しまたはURLなし')
            aid = hashlib.sha256((publisher + '\n' + url).encode()).hexdigest()[:24]
            articles[aid] = {'id': 'media:' + aid, 'source': 'media', 'publisher': publisher,
                             'title': title, 'url': url, 'published': published.isoformat(),
                             'date': published.date().isoformat(), 'voice': publisher}
        except (ValueError, TypeError, OverflowError):
            invalid += 1
    return list(articles.values()), invalid


def refresh(cfg, *, force=False, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    cache = store.load_json('media.json', {'publishers': {}, 'articles': {}})
    cutoff = (now.date() - timedelta(days=int(cfg.windows.get('keep_docs_days', 120)))).isoformat()
    specs = cfg.raw.get('media', {}).get('publishers', {})
    for key, spec in specs.items():
        status = cache['publishers'].setdefault(key, {'coverage': {}})
        checked = status.get('checked_at')
        interval = int(cfg.raw.get('media', {}).get('refresh_minutes', 180)) * 60
        if not force and checked and 0 <= (now - datetime.fromisoformat(checked)).total_seconds() < interval:
            continue
        status['checked_at'] = now.isoformat()
        if spec.get('enabled', True) is False:
            status.update(status='disabled', error='設定で停止中')
            continue
        try:
            r = http.get(spec['feed'], timeout=25, retries=2)
            if r is None or r.status_code != 200:
                raise ValueError('応答なし' if r is None else f'HTTP {r.status_code}')
            articles, invalid = parse_feed(r.content, key, spec)
            valid = [a for a in articles if a['published'] <= now.isoformat() and a['date'] >= cutoff]
            if not valid:
                raise ValueError('日付つきの新しい見出しを確認できません')
            for a in valid:
                a['fields'] = sorted(set(cfg.fields_for_text(a['title'])) | set(spec.get('fields', [])))
                cache['articles'][a['id']] = a
            oldest = min(datetime.fromisoformat(a['published']) for a in valid)
            d = oldest.date()
            while d <= now.date():
                # 検索結果には件数上限がある。全件取得とみなさない。
                full = (not invalid and spec.get('method') != 'search' and
                        oldest <= datetime.combine(d, time.min, timezone.utc) and d < now.date())
                prev = status['coverage'].get(d.isoformat())
                status['coverage'][d.isoformat()] = 'covered' if full or prev == 'covered' else 'partial'
                d += timedelta(days=1)
            status.update(status='ok', error=None, last_success=now.isoformat(),
                          latest=max(a['published'] for a in valid), received=len(valid), invalid=invalid)
            log.info('%s: 見出し%d件%s', spec['label'], len(valid), f' / 不正な項目{invalid}件' if invalid else '')
        except Exception as exc:
            status.update(status='error', error=str(exc)[:150])
            log.warning('%s: 取得失敗 (%s)。保存済みの見出しは保持します', spec['label'], exc)
    unique = {}
    for a in cache['articles'].values():
        if a['date'] >= cutoff and a['publisher'] in specs:
            unique.setdefault((a['publisher'], a['date'], title_key(a['title'])), a)
    cache['articles'] = {a['id']: a for a in unique.values()}
    cache['publishers'] = {k: s for k, s in cache['publishers'].items() if k in specs}
    for status in cache['publishers'].values():
        status['coverage'] = {d: v for d, v in status.get('coverage', {}).items() if d >= cutoff}
    store.save_json('media.json', cache)
    return cache


def fetch_day(day: date) -> list[dict]:
    return [a for a in store.load_json('media.json', {}).get('articles', {}).values()
            if a['date'] == day.isoformat()]


def term_daily_counts(term: str, start: date, end: date) -> dict[str, dict] | None:
    cache = store.load_json('media.json', {})
    if not cache.get('publishers'):
        return None
    hits = defaultdict(set)
    voices = defaultdict(set)
    for a in cache.get('articles', {}).values():
        if matches(term, a['title']):
            hits[a['date']].add(a['url'])
            voices[a['date']].add(a['publisher'])
    result = {}
    d = start
    while d <= end:
        key = d.isoformat()
        cov = [s.get('coverage', {}).get(key) for s in cache['publishers'].values()]
        observed = any(cov) or key in hits
        result[key] = {'count': len(hits[key]) if observed else None,
                       'voices': len(voices[key]) if observed else None,
                       'partial': not cov or not all(c == 'covered' for c in cov)}
        d += timedelta(days=1)
    return result


def unique_documents(docs: list[dict]) -> list[dict]:
    """同一記事がHN・ニュース・RSSに重複したら1件。経路だけで加点しない。"""
    urls, out = set(), []
    media_titles = {title_key(d['title']) for d in docs if d['source'] == 'media'}
    for doc in sorted(docs, key=lambda d: d['source'] != 'media'):
        url = canonical_url(doc.get('url', ''))
        if not url and doc['source'] == 'news' and doc['id'].startswith('news:http'):
            url = canonical_url(doc['id'][5:])
        if (url and url in urls) or (doc['source'] in ('hn', 'news') and title_key(doc['title']) in media_titles):
            continue
        if url:
            urls.add(url)
        out.append(doc)
    return out
