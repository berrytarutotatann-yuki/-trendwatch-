"""共通の HTTP 取得。サイトごとに間隔を空け、失敗したら少し待って再試行する。"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

# サイトごとの最低間隔（秒）。各サービスの利用ルールに合わせている
MIN_INTERVAL = {
    "export.arxiv.org": 3.2,   # arXiv API は3秒に1回まで
    "api.gdeltproject.org": 5.5,  # GDELT は5秒に1回まで
    "hn.algolia.com": 0.3,
    "qiita.com": 1.0,
}
_last_call: dict[str, float] = {}

_session = requests.Session()
_session.headers["User-Agent"] = "trendwatch/0.1 (personal research; +https://github.com/)"


def get(url: str, params: dict | None = None, headers: dict | None = None,
        retries: int = 3, timeout: int = 40, ok_statuses=(200,)) -> requests.Response | None:
    host = urlparse(url).hostname or ""
    wait = MIN_INTERVAL.get(host, 0.5)
    for attempt in range(retries):
        since = time.monotonic() - _last_call.get(host, 0)
        if since < wait:
            time.sleep(wait - since)
        _last_call[host] = time.monotonic()
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            log.warning("GET %s 失敗 (%s) 再試行 %d/%d", host, e, attempt + 1, retries)
            time.sleep(wait * (attempt + 2))
            continue
        finally:
            # 応答に時間がかかった場合も、次の通信まで最低間隔を空ける。
            _last_call[host] = time.monotonic()
        if r.status_code in ok_statuses:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            log.warning("GET %s -> %s 再試行 %d/%d", host, r.status_code, attempt + 1, retries)
            time.sleep(max(wait, 5) * (attempt + 2))
            continue
        return r  # 404 など：呼び出し側で判断
    return None
