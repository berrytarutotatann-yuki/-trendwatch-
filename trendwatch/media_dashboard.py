"""保存済みの見出しから媒体別の可視化用データを作る（通信しない）。"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import store
from .sources.media import matches
from .textproc import phrases


def pack_media(cfg, tracked, discovery):
    cache = store.load_json('media.json', {})
    specs = cfg.raw.get('media', {}).get('publishers', {})
    today = datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=int(cfg.windows.get('series_days', 120)) - 1)).isoformat()
    articles = [a for a in cache.get('articles', {}).values()
                if a['publisher'] in specs and cutoff <= a['date'] <= today.isoformat()]
    articles.sort(key=lambda a: a['published'], reverse=True)
    terms = {t: v.get('field', 'other') for t, v in tracked.items()}
    for rows in (discovery or {}).get('fields', {}).values():
        for r in rows:
            terms.setdefault(r['term'], r['field'])
    # 保存データが少ない初日も、媒体をまたいで現れた言葉を選べる。
    publishers, counts = defaultdict(set), defaultdict(int)
    fields = defaultdict(Counter)
    recent = (today - timedelta(days=6)).isoformat()
    excluded = cfg.exclude_regexes()
    for a in articles:
        if a['date'] < recent:
            continue
        for p in phrases(a['title']):
            if any(rx.search(p) for rx in excluded):
                continue
            publishers[p].add(a['publisher'])
            counts[p] += 1
            fields[p].update(a.get('fields', []))
    candidates = sorted(publishers, key=lambda p: (-len(publishers[p]), -counts[p], p))
    for p in candidates[:40]:
        if counts[p] >= 2:
            terms.setdefault(p, fields[p].most_common(1)[0][0] if fields[p] else 'other')
    packed_terms = []
    for term, field in terms.items():
        found = [a for a in articles if matches(term, a['title'])]
        daily = defaultdict(lambda: defaultdict(int))
        for a in found:
            daily[a['publisher']][a['date']] += 1
        packed_terms.append({'term': term, 'field': field, 'daily': dict(daily),
                             'articles': [a['id'] for a in found]})
    catalog = []
    for key, spec in specs.items():
        status = cache.get('publishers', {}).get(key, {})
        catalog.append({'key': key, 'label': spec['label'], 'site': spec['site'],
                        'method': spec.get('method', 'rss'), 'status': status.get('status', 'pending'),
                        'checked_at': status.get('checked_at'), 'last_success': status.get('last_success'),
                        'latest': status.get('latest'), 'error': status.get('error'),
                        'coverage': status.get('coverage', {}),
                        'count': sum(a['publisher'] == key for a in articles)})
    return {'end': today.isoformat(), 'publishers': catalog, 'terms': packed_terms,
            'articles': {a['id']: {k: a[k] for k in ('title', 'url', 'publisher', 'date', 'published', 'fields')}
                         for a in articles}}
