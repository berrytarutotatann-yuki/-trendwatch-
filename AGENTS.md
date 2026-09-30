# AGENTS.md

（Codex などの AI 向け。内容は CLAUDE.md と同じ。最初に HANDOFF.md を読むこと）

このリポジトリは「流行りかけの技術用語を見つけ、日ごとの言及数をグラフにする」Python ツール。
持ち主は日本語話者でプログラミング初心者。説明は日本語で、専門用語は短く言い換えること。

## 構成
- `config.yaml` … 分野（fields）、手動追跡語（tracked_terms）、しきい値。まずここで解決できないか考える
- `trendwatch/collect.py` … 1日分の見出しを HN / arXiv / GDELT / 指定媒体の保存済み見出しから集めて `data/docs/YYYY-MM-DD.jsonl.gz` に保存
- `trendwatch/discover.py` … 2〜3語フレーズを抽出し、ポアソン z 値 × データ源数ボーナスで点数化。結果は `data/discovery/`
- `trendwatch/track.py` … 追跡語ごとに各データ源の日別件数を `data/series.json` へ（初回120日、以降は直近14日を取り直し）
- `trendwatch/dashboard.py` + `template.html` … `docs/index.html` を生成（データ埋め込み・外部ライブラリなし・ライト/ダーク対応）
- `trendwatch/sources/*.py` … 各 API。`fetch_day()` と `term_daily_counts()` を持つ
- `trendwatch/sources/media.py` … 指定10媒体のRSS/Atomを `data/media.json` に保存。ReutersのみGoogleニュース検索経由。本文は保存しない
- `trendwatch/media_dashboard.py` … 媒体別の掲載日・掲載媒体数・記事リンクを可視化用に集計
- `.github/workflows/media.yml` … 3時間ごとに媒体収集とページ更新（`python -m trendwatch media`）
- `.github/workflows/daily.yml` … 毎日 21:10 UTC。`backfill.yml` … 初回手動

## 約束ごと
- 日付は UTC。`term_daily_counts` は `{日付: {"count", "voices"}}`、取得失敗は `None`（0件と区別する）
- API の間隔は `trendwatch/http.py` の MIN_INTERVAL で守る（arXiv 3秒、GDELT 5秒）。縮めないこと
- 指定媒体の未取得日は `count: None`、一部取得日は `partial: True`。取得前の期間を0件で埋めない
- 1つのデータ源の失敗で全体を止めない
- 変更したら `python -m pytest` を通す。ネットに出るテストは書かない（monkeypatch で差し替える）
- ページを変えたら `python -m trendwatch build` で作り直し、ブラウザで開いて確認する

## よくある依頼
- 分野追加 → `config.yaml` の fields に arxiv_categories / news_query / keywords を追加
- ノイズ除去 → `config.yaml` の exclude_patterns か `data/exclude.txt`、`textproc.py` の STOPWORDS
- 新しいデータ源 → `sources/` にモジュールを追加し、collect.py（発見用）と track.py の SOURCES（グラフ用）、template.html の SRC に登録
