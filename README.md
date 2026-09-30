# トレンド語ウォッチ（trendwatch）

海外の技術系の場所（Hacker News・arXiv論文・英語ニュース）で**急に増え始めた言葉**を毎朝見つけて、
言葉ごとの**日ごとの言及数をグラフ**にするシステムです。分野は AI・半導体・電力。

- 毎朝6時10分ごろ（日本時間）に GitHub Actions が自動で動く
- 結果は GitHub Pages のページ（`docs/index.html`）で、スマホからも見られる
- AI は使わないので、利用料はかからない（GitHub の無料枠で動く）

> このシステムは「調べる候補を見つける」ためのものです。投資の助言ではありません。

---

## ページの見方

**新語候補**：最近7日の見出しに急に増えた2〜3語のフレーズ。

| 列 | 意味 |
|---|---|
| 点数 | 過去90日のペースから予想される件数より、どれだけ多いか。2以上で「はっきり多い」、10以上はかなり急 |
| 最近7日 / 予想 | 実際の件数と、過去のペースなら何件のはずだったか |
| 人数 | 何人（何サイト）が使ったか。1人の連投では上がらない |
| 出た場所 | HN・arXiv・ニュースのどこに出たか。複数の場所に出ているほど点数が上がる |

**追跡中の言葉**：言葉ごとのカード。Hacker News・arXiv・英語ニュース・Qiita（日本語）の
日ごとの件数を縦に並べています。

- 「伸び」：直近7日が、その前4週のペースよりどれだけ多いか（点数と同じ考え方）
- 「日本語圏ではまだ0件」：英語圏で直近30日に10件以上あるのに、Qiita では0件
- 株価の行：`config.yaml` で銘柄を指定した言葉だけ出る

### 点数の計算方法

単純な「新しさ×伸び」ではなく、こうしています（`trendwatch/discover.py`）。

```
予想   = 過去の件数 × (7日 ÷ 過去の日数)
z      = (最近7日の件数 − 予想) ÷ √(予想 + 1)
点数   = z × (1 + 0.5 × (出た場所の数 − 1))
```

- 過去が0件でも無限大にならない
- 件数が少ないうちは点数が控えめになる（1件→3件のような偶然で跳ねない）
- 3人以上が使っていないと候補にしない

---

## はじめ方（GitHub で動かす）

必要なもの：GitHub アカウント（無料）

1. **GitHub に新しいリポジトリを作る**
   github.com → 右上の「+」→ New repository。名前は `trendwatch` など。
   Public にすると Pages が無料で使えます（Private の Pages は有料プラン）。
2. **このフォルダの中身をアップロード**
   リポジトリの画面で「uploading an existing file」から、このフォルダの中身を全部ドラッグ＆ドロップ。
   `.github` フォルダ（隠しフォルダ）も忘れずに。見えないときは下の「Claude Code で」の方法が確実です。
3. **Actions に書き込み権限を与える**
   Settings → Actions → General → 一番下の Workflow permissions →
   「Read and write permissions」を選んで Save。
4. **過去データを集める（最初の1回だけ）**
   Actions タブ → 左の「backfill」→ Run workflow。
   過去97日分を集めるので **1.5〜3時間**かかります。終わるまで待ちます。
5. **ページを公開する**
   Settings → Pages → Source を「Deploy from a branch」、Branch を `main`、フォルダを `/docs` にして Save。
   数分後に `https://ユーザー名.github.io/trendwatch/` で見られます。

以後は毎朝自動で更新されます。

### （任意）Qiita のトークン

Qiita は登録なしだと1時間60回までです。追跡語が増えると足りなくなるので、
Qiita の 設定 → アプリケーション → 個人用アクセストークン（read_qiita だけでOK）を発行して、
GitHub の Settings → Secrets and variables → Actions → New repository secret に
名前 `QIITA_TOKEN` で登録すると1時間1000回になります。

---

## Claude Code で動かす・直す

パソコンの Claude Code でこのフォルダを開けば、そのまま頼めます。例：

- 「このフォルダを GitHub の新しいリポジトリとして push して」
- 「ローカルで一度動かして、結果のページを開いて」
- 「分野にバイオを追加して」
- 「候補にニュースのノイズが多いので減らして」

`CLAUDE.md` にこのプロジェクトの構成を書いてあるので、Claude Code はそれを読んで作業します。

### 自分のパソコンで動かす場合

```bash
pip install -r requirements.txt
python -m trendwatch backfill --days 97   # 最初の1回（時間がかかる）
python -m trendwatch daily                # 毎日の処理
open docs/index.html                      # Windows は start docs/index.html
```

---

## よく使う設定（config.yaml）

- **追跡する言葉を足す**：`tracked_terms` に追加。`tickers` に銘柄を書くと株価も並ぶ
  （日本株は `8035.T` のように `.T` を付ける）
  コマンドでも追加できる：`python -m trendwatch add "glass substrate" --field semiconductor`
- **いらない候補を消す**：`python -m trendwatch exclude "new york"`（`data/exclude.txt` に追記される）
- **分野を増やす**：`fields` に同じ形で追加（arXiv カテゴリ・ニュース検索式・振り分け用の単語）
- **厳しさを変える**：`discovery` の `min_voices`（最低人数）、`min_score`（表示する最低点数）

毎日、各分野の上位2件（点数4以上）が自動で追跡に入り、30日で外れます。
残したいものは `add` コマンドか `tracked_terms` に書けば外れません。

---

## データ源と注意

| 場所 | 使っているもの | 注意 |
|---|---|---|
| Hacker News | Algolia の公開検索API | 登録不要 |
| arXiv | 公開API | 3秒に1回まで（自動で守る） |
| 英語ニュース | GDELT | 5秒に1回まで・約3か月前までしか取れない |
| Qiita | 公開API | 上の「Qiita のトークン」参照 |
| 株価 | yfinance | 非公式のため止まることがある。止まっても他は動く |

- 日付はすべて UTC 基準です。
- この環境で作成したときは外部サイトに接続できなかったため、各API の動作は
  テスト用のデータで確認しています。最初の backfill のあと、Actions のログにエラーが出ていないか
  一度見てください（「取得失敗」「JSON でない応答」が続くときは Claude Code に直してもらってください）。
- GitHub は60日間リポジトリに動きがないと定期実行を止めることがあります。毎日の自動コミットで
  通常は止まりませんが、止まったら Actions タブから再度有効にしてください。
- SNS のアカウント名を「使う予定なく確保」することは各サービスの規約違反になりうるので、
  このシステムには入れていません。

## ファイル構成

```
config.yaml                 設定（分野・追跡語・しきい値）
trendwatch/
  cli.py                    コマンド
  collect.py                1日分の見出しを集める
  discover.py               新語候補の点数計算
  track.py                  追跡語の日ごとの件数
  dashboard.py + template.html  グラフのページ
  sources/                  各データ源（hn, arxiv, gdelt, qiita）
  prices.py                株価
data/                       集めたデータ（自動で増える）
docs/index.html             公開されるページ
.github/workflows/          毎日の実行（daily）と初回用（backfill）
tests/                      テスト（python -m pytest）
```

## 指定媒体の見出しと「メディアへの広がり」

Bloomberg Markets、Reuters Business、TechCrunch、The Verge、Forbes Innovation、
WSJ Tech、The Information に加え、以下の専門媒体を監視します。

- **Semiconductor Engineering**: 半導体の設計・製造・実装の専門報道。
- **Utility Dive**: 電力会社、送電網、蓄電池、データセンター電力などの業界報道。
- **IEEE Spectrum**: 工学・研究・技術の実用化を扱う報道。

設定は `config.yaml` の `media.publishers` です。本文は保存せず、公開フィードの見出し・公開日時・記事リンクを保存します。
Reuters BusinessだけはGoogleニュースの検索RSS経由です。公式配信と検索経由は画面で区別しています。

すぐに見出しを収集してページを更新するには:

```bash
python -m trendwatch media
```

通常の `daily` にも組み込んであります。さらに `.github/workflows/media.yml` は3時間ごとに
指定媒体だけを収集します。GitHubに反映してActionsを有効にすると実行されます。
RSSには直近の少数記事しか残らないため、こまめに保存して履歴を増やします。
過去120日分の全記事を取り戻す機能ではありません。

ページの「メディアへの広がり」でできること:

1. 言葉と期間（14・30・90日）を選び、掲載が確認できた媒体数と見出し数を見る。
2. 日付×媒体の色分け表で広がった時期を比べる。
3. マスを押して該当する見出しを表示し、元の記事へ進む（Reutersは検索サービス経由）。
4. 「監視する媒体の一覧」を開き、取得状況や最後に取得できた日を見る。

表の `—` は未取得、斜線と `*` は一部取得です。`0` は取得した配信内に該当見出しがないという意味で、
その媒体の全記事に言及がないことは意味しません。今日の分、検索経由、フィードの開始日、
日付等の不正な項目がある取得は一部取得扱いです。取得失敗時は前回のデータを保持します。
掲載媒体数も、独立した取材の数を保証するものではありません。

新語の発見にも媒体の見出しを使います。同じURLの記事（追跡用のURLパラメータを除く）、
RSSとHN/GDELTにある同一の見出しは重複して数えません。
従来の言及数グラフにも「指定媒体の見出し」を追加しましたが、HN/GDELTとの重複があるため
「英語圏」の合計には加算しません。媒体ごとの色分け表は当日分も含み、従来のグラフは昨日までです。

保存先は `data/media.json` です。過去の配信を数えるために必要な見出しと取得範囲を蓄積し、
`keep_docs_days` より古いものを削除します。媒体だけの取得で、他の情報源まで取得済みとは扱いません。
