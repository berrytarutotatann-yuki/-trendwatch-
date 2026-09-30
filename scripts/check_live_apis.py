"""手動の実API確認（pytestからは実行しない）。"""
from datetime import date, datetime, timedelta, timezone
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trendwatch import http
from trendwatch.sources import hn, arxiv, gdelt, qiita


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date() - timedelta(days=1))
    args = parser.parse_args()
    end = args.date
    start = end - timedelta(days=119)
    lo, _ = hn.day_bounds(start)
    _, hi = hn.day_bounds(end)
    for advanced in ('false', 'true'):
        r = http.get(hn.BASE, params={'query': '"slop ui"', 'advancedSyntax': advanced,
                     'typoTolerance': 'false', 'tags': '(story,comment)',
                     'numericFilters': f'created_at_i>={lo},created_at_i<{hi}', 'hitsPerPage': 1000})
        js = r.json() if r is not None else {}
        print('HN advancedSyntax', advanced, 'hits', js.get('nbHits'), flush=True)
    for name, fn, term in [('hn', hn.term_daily_counts, 'slop ui'),
                            ('arxiv', arxiv.term_daily_counts, 'language model'),
                            ('qiita', qiita.term_daily_counts, 'Python')]:
        got = fn(term, end, end)
        print(name, term, got, flush=True)
    r = http.get(gdelt.BASE, params={'query':'"power grid"', 'mode':'timelinevolraw', 'format':'json',
                   'startdatetime':f'{end - timedelta(days=1):%Y%m%d}000000', 'enddatetime':f'{end:%Y%m%d}235959'})
    js = gdelt._json(r)
    print('GDELT timeline', None if js is None else gdelt.parse_timeline(js), flush=True)
    r = http.get(gdelt.BASE, params={'query':'"power grid" sourcelang:english', 'mode':'artlist',
                 'format':'json', 'maxrecords':250, 'startdatetime':f'{end:%Y%m%d}000000','enddatetime':f'{end:%Y%m%d}235959'})
    js = gdelt._json(r)
    print('GDELT articles', None if js is None else len(js.get('articles', [])), flush=True)
    from trendwatch.prices import fetch_closes
    got = fetch_closes(['MU'], 5)
    print('yfinance', {k: len(v) for k,v in got.items()}, flush=True)

if __name__ == '__main__':
    main()
