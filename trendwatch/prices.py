"""株価（任意）。yfinance が入っていて、config の tracked_terms に tickers があるときだけ動く。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


def fetch_closes(tickers: list[str], days: int) -> dict[str, dict[str, float]]:
    if not tickers:
        return {}
    try:
        import yfinance as yf
    except ImportError:
        log.info("yfinance が無いので株価はスキップします")
        return {}
    out: dict[str, dict[str, float]] = {}
    start = datetime.now(timezone.utc).date() - timedelta(days=days + 5)
    for t in sorted(set(tickers)):
        try:
            df = yf.download(t, start=start.isoformat(), progress=False, auto_adjust=True)
            if df is None or df.empty:
                continue
            close = df["Close"]
            if hasattr(close, "columns"):  # 新しい yfinance は列が2段になる
                close = close.iloc[:, 0]
            out[t] = {idx.date().isoformat(): round(float(v), 4)
                      for idx, v in close.dropna().items()}
        except Exception as e:  # 1銘柄の失敗で全体を止めない
            log.warning("株価取得失敗 %s: %s", t, e)
    return out
