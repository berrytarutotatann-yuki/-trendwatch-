"""コマンド一覧:

  python -m trendwatch daily              毎日の処理を全部（集める→候補を出す→グラフ更新→ページ作成）
  python -m trendwatch backfill --days 97 過去の見出しをまとめて集める（最初に1回）
  python -m trendwatch collect --date 2026-09-27
  python -m trendwatch discover [--date ...]
  python -m trendwatch track [--term "slop ui"]
  python -m trendwatch media              指定媒体だけ収集してページ更新
  python -m trendwatch build              グラフのページ(docs/index.html)だけ作り直す
  python -m trendwatch add "言葉" --field ai   追跡に手動で追加（自動では外れない）
  python -m trendwatch exclude "言葉"          今後の候補から外す
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta, timezone

from . import store
from .collect import collect_day
from .config import data_dir, load_config
from .dashboard import build
from .discover import auto_track, run_discovery
from .prices import fetch_closes
from .track import tracked_terms, update_series
from .sources import media

log = logging.getLogger("trendwatch")


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _date(s: str | None, default: date) -> date:
    return date.fromisoformat(s) if s else default


def cmd_daily(cfg, args):
    today = utc_today()
    yesterday = today - timedelta(days=1)
    # 昨日まで（今日はまだ途中なので集めない）。取り逃した日があれば直近5日分は埋める
    for i in range(5, 0, -1):
        d = today - timedelta(days=i)
        if not store.has_day(d) or d == yesterday:
            n = collect_day(cfg, d)
            log.info("%s: %d件保存", d, n)
    store.prune_docs(int(cfg.windows.get("keep_docs_days", 120)), today)
    result = run_discovery(cfg, yesterday)
    added = auto_track(cfg, result, today)
    if added:
        log.info("自動追跡に追加: %s", ", ".join(added))
    update_series(cfg, yesterday)
    update_prices(cfg)
    build(cfg)


def update_prices(cfg):
    tickers = sorted({t for v in tracked_terms(cfg).values() for t in v.get("tickers") or []})
    if tickers:
        closes = fetch_closes(tickers, int(cfg.windows.get("series_days", 120)))
        if closes:
            old = store.load_json("prices.json", {})
            old.update(closes)
            store.save_json("prices.json", {t: old[t] for t in tickers if t in old})


def cmd_backfill(cfg, args):
    today = utc_today()
    for i in range(args.days, 0, -1):
        d = today - timedelta(days=i)
        if store.has_day(d) and not args.force:
            continue
        n = collect_day(cfg, d)
        log.info("%s: %d件保存 (残り%d日)", d, n, i - 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="trendwatch", description="流行りかけの技術用語を見つけてグラフにする")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("daily")
    s = sub.add_parser("backfill"); s.add_argument("--days", type=int, default=97)
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("collect"); s.add_argument("--date")
    s = sub.add_parser("discover"); s.add_argument("--date")
    s = sub.add_parser("track"); s.add_argument("--term", action="append")
    sub.add_parser("build")
    sub.add_parser("media", help="指定媒体の見出し収集とページ更新")
    s = sub.add_parser("add"); s.add_argument("term"); s.add_argument("--field", default="other")
    s = sub.add_parser("exclude"); s.add_argument("term")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config()
    yesterday = utc_today() - timedelta(days=1)

    if args.cmd == "daily":
        cmd_daily(cfg, args)
    elif args.cmd == "backfill":
        cmd_backfill(cfg, args)
    elif args.cmd == "collect":
        d = _date(args.date, yesterday)
        log.info("%s: %d件保存", d, collect_day(cfg, d))
    elif args.cmd == "discover":
        r = run_discovery(cfg, _date(args.date, yesterday))
        for key, rows in r["fields"].items():
            print(f"\n== {key} ==")
            for row in rows:
                print(f"{row['rank']:>2}. {row['term']:<35} score={row['score']:>6}  "
                      f"最近{row['recent']} / 過去{row['baseline']}  {','.join(row['sources'])}")
    elif args.cmd == "track":
        update_series(cfg, yesterday, only=args.term)
    elif args.cmd == "media":
        media.refresh(cfg, force=True)
        run_discovery(cfg, yesterday)
        # 既存APIへの通信はせず、保存済み見出しの系列だけ更新する。
        update_series(cfg, yesterday, sources={"media": media.term_daily_counts})
        print(build(cfg))
    elif args.cmd == "build":
        print(build(cfg))
    elif args.cmd == "add":
        tracked = store.load_json("tracked.json", {})
        tracked[args.term.lower()] = {"field": args.field, "origin": "manual", "pinned": True,
                                      "added": utc_today().isoformat()}
        store.save_json("tracked.json", tracked)
        print(f"追加しました: {args.term}（次回の daily / track でグラフに出ます）")
    elif args.cmd == "exclude":
        f = data_dir() / "exclude.txt"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(args.term.strip().lower() + "\n")
        print(f"除外しました: {args.term}")


if __name__ == "__main__":
    main()
