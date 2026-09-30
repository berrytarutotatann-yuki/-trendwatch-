"""データ源。各モジュールは2つの役割を持つ。

- fetch_day(...)          : ある1日の見出しを集める（新語を見つける用）
- term_daily_counts(...)  : 指定した言葉の日ごとの言及数を数える（グラフ用）

term_daily_counts は {"YYYY-MM-DD": {"count": int, "voices": int | None}} を返す。
"""
from datetime import date, datetime, timedelta, timezone


def day_bounds(day: date) -> tuple[int, int]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def ts_to_day(ts: int | float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
