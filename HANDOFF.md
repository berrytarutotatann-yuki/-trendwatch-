# 引き継ぎメモ（Claude → 次の担当 AI）

作成日: 2026-09-29。このファイルを最初に読んでください。構成とルールは `AGENTS.md` にあります。

## 1. ユーザーについて
- 日本語話者で、プログラミングは初心者。説明は日本語で、専門用語は短く言い換えること
- 目的：海外の技術系の場所で**流行りかけている言葉**を早めに見つけて、日ごとの言及数をグラフで見たい。
  将来は株を調べる候補探しにも使いたい（自動売買ではない。投資の助言はしないこと）
- 追う分野：AI・半導体・電力
- 動かす場所：ユーザー自身の GitHub（GitHub Actions で毎朝実行、GitHub Pages で閲覧）

## 2. ここまでの経緯（要点）
- **ドメイン取得・転売はやめた**（ユーザーの判断）。目的は「流行りかけの言葉を見つけてグラフで見ること」だけ。
  ドメインや SNS アカウント名の確保に関わる機能は追加しないこと。
  2026-09-29 の引き継ぎ作業で、ユーザーの依頼により `.com` 空き確認の処理・表示・設定を削除済み。
- 点数は単純な「新しさ×伸び」ではなく、**ポアソン z 値**
  `(最近の件数 − 予想) / √(予想 + 1)`、`予想 = 過去の件数 × 7/過去の日数`、
  に「出てきたデータ源の数」のボーナスを掛けたもの。条件は「3人以上が使っている」こと（1人の連投対策）
- 手動の試し調査（2026-09-28、HN の直近30日と前90日の比較）では、
  「system one model」（13件 / 0件）と「slop ui」（11件 / 6件）が伸びていた。
  「harness engineering」は件数は多いがピークを過ぎていた
- 注意：HN Algolia で短い単語（例「Jev」）を検索すると、似た綴りまで拾ってしまう。
  そのため `typoTolerance=false` を付け、2〜3語のフレーズで数えている

## 3. 現在の状態
- 完成：収集（HN / arXiv / GDELT）、候補の点数計算、追跡語の日別件数（HN / arXiv / GDELT / Qiita）、
  株価（yfinance、任意）、ページ生成、GitHub Actions、README
- `python -m pytest` → 11件すべて成功
- 架空データでページを生成し、PC・スマホ・ダークモードで表示崩れがないことを確認済み

## 4. まだ確認できていないこと（最優先）
以下は引き継ぎ時点の記録。2026-09-29 の実API確認結果は末尾の「7」を参照。
Claude の作業環境は外部 API に接続できなかったため、引き継ぎ時点では実際の API に対して未確認だった。
データの形は、HN Algolia と arXiv については事前に確認した実データに合わせてある。
GDELT・Qiita・yfinance は、公開されている仕様を覚えている範囲で書いただけで、実物で確かめていない。

確認手順の案：
1. `pip install -r requirements.txt`
2. `python -m trendwatch -v collect --date <昨日>` → HN・arXiv・ニュースの件数がログに出るか
3. `python -m trendwatch discover` → 候補が出るか（過去データが無いので「初登場」ばかりになるのは正常）
4. `python -m trendwatch track --term "slop ui"` → `data/series.json` に各データ源の数字が入るか
5. `python -m trendwatch build` → `docs/index.html` を開いて確認

特に怪しい箇所：
- `sources/gdelt.py`：`timelinevolraw` の日付の形式と解像度、`artlist` の `startdatetime` の指定、混雑時に文章でエラーが返る場合の扱い
- `sources/qiita.py`：`created:>=` の検索式が効くか
- `sources/hn.py`：クエリを引用符で囲んだときにフレーズ一致になるか（`advancedSyntax` が必要かどうか）
- `prices.py`：yfinance の新しい版では列が2段になる（MultiIndex）ので、その対応が正しく動くか

## 5. 次にやること（ユーザーの手順）
1. 上の 4 の確認と修正
2. GitHub にリポジトリを作って push（Public 推奨。Private だと Pages が有料になる）
3. Settings → Actions → Workflow permissions を「Read and write」にする
4. Actions の「backfill」を手動で実行（1.5〜3時間）
5. Settings → Pages で `main` ブランチの `/docs` を公開
6. （任意）Qiita のトークンを Secrets に `QIITA_TOKEN` という名前で登録

## 6. 今後やりたいと出ていた案（まだ手を付けていない）
- 言葉と関連する上場企業の対応付け（今は `config.yaml` の `tickers` に手で書く方式）
- 過去データを使った検証：候補に上がった言葉のあと、関連株がどう動いたか
- 日本語圏での広がりを見るデータ源の追加（Zenn、はてなブックマークなど）

## 7. 2026-09-29 の引き継ぎ作業（Codex）

### 実API確認
- `pip install -r requirements.txt` を実行済み。
- 2026-09-28（UTC）の見出し取得: HN 1,151件、arXiv 743件。
- HN の `slop ui`: 120日間で16件。`advancedSyntax=false` だと141件、`true` だと16件になることを実APIで比較。明示的に `true` を指定するよう変更。
- arXiv の `slop ui`: 正常なXML応答で0件。追加の `language model` 検索は429とタイムアウトで完了せず。見出し取得は成功している。
- Qiita: `slop ui` は0件。別途 `Python` を検索し、2026-09-28 UTC の113件・99人を取得。検索日は前後を広く取り、記事の時刻をUTCに直して対象日だけ数える。
- GDELT: `power grid` の `timelinevolraw` は実データを取得。`20260927T001500Z` のような15分単位の応答で、既存の日別合算に合致。
- GDELTの見出し検索は一部200の応答があったものの、429（回数制限）が繰り返され、1日分の収集は完了できていない。正常な日別データを含まない空の応答もあるため、それを0件として保存しない。ニュースの完全な取得成功は未確認。
- 任意の株価機能も `MU` で確認し、7営業日分の終値を取得。
- 手動で再確認する補助スクリプト: `python scripts/check_live_apis.py --date 2026-09-28`。これはネットに接続するため、pytestには含めていない。実API確認は同時に複数起動せず、順番に実行する。

### 修正点
- `.com` 空き確認の本体、コマンドのオプション、設定、ページの列、出典表示、README、関連テストを削除。
- HN / arXiv / GDELT / Qiita の取得失敗・途中までしか取得できなかった場合を `None` として扱い、前回の集計を保持。arXivの取得上限・Qiitaのページ上限で切れた集計も保存しない。
- 見出し収集も、1つのデータ源で例外が発生しても他のデータ源を続ける。失敗したデータ源の保存済み見出しは残す。
- グラフは最後に取得できた日より後を0件で埋めない。
- API通信は応答完了後にも最低間隔を空ける。既存のarXiv 3.2秒、GDELT 5.5秒は維持。
- 株価の開始日もUTC基準に統一。

### 参照した公式仕様
- Algolia の語順一致: https://www.algolia.com/doc/api-reference/api-parameters/advancedSyntax
- Qiita の日付検索: https://help.qiita.com/ja/articles/qiita-search-options
- GDELT の時系列: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

### 検証
- `python -m pytest`: 23件すべて成功。テスト中は外部APIに接続しない。
- 検証内容: 取得失敗と0件の区別、途中取得の失敗、検索語順の設定、QiitaのUTC境界、古いデータの保持、通信間隔、ドメイン表示の削除。
- 最終の収集ファイルを読み直し、HN 1,151件 + arXiv 743件 = 1,894件の保存を確認。
- `python -m trendwatch discover`: 26候補を生成。比較用の過去データはまだ0日なので、「初登場」は実際に新しい言葉であることを保証しない。
- `python -m trendwatch build` で `docs/index.html` を再生成。
- 最終ページをChromiumでPC（1440px）・スマホ（390px）・ダーク表示で確認。ページの横はみ出し、JavaScriptエラー、`.com`列がないことを確認。確認環境には日本語フォントがなかったので、一時フォルダのフォントをブラウザに読み込んだ（配布ページに外部依存は追加していない）。
- 今回の追跡更新は手順通り `slop ui` のみ。ほかの設定済み追跡語は今後の `track` / `daily` で取得する。

## 8. 2026-09-29 指定媒体の収集と可視化

ユーザーの依頼で7媒体とおすすめの3媒体を追加。

| 媒体 | 取得経路 | 初回保存件数 |
| --- | --- | ---: |
| Bloomberg Markets | 公式RSS | 20 |
| Reuters Business | Googleニュース検索RSS（Reutersの出典だけ許可） | 100 |
| TechCrunch | 公式RSS | 20 |
| The Verge | 公式Atom | 10 |
| Forbes Innovation | 公式RSS | 25 |
| WSJ Tech | Dow Jonesの公式RSS | 33 |
| The Information | 公式Atom | 20 |
| Semiconductor Engineering | 公式RSS | 10 |
| Utility Dive | 公式RSS | 10 |
| IEEE Spectrum | 公式RSS | 27 |

計275件。2026-09-29 UTCに実際に取得した公開フィードから保存したもの。将来日付・保持期限より古い項目を除く。
追加の3媒体は、半導体の設計/製造、電力業界、工学/技術の報道を補うために選定。

### 操作と自動更新
- `python -m trendwatch media`: 指定媒体だけ収集し、候補・媒体の時系列・ページを更新。HN/arXiv/GDELTへの追加通信はしない。
- 既存の `collect` / `daily` にも統合。短時間の繰り返し取得は3時間のキャッシュで抑える。
- `.github/workflows/media.yml`: 3時間ごとに同じコマンドを実行。dailyと同じconcurrencyグループで同時書き込みを防ぐ。GitHubへの反映・公開は今回未実施。
- ページ先頭の「メディアへの広がり」で言葉・期間を選択。媒体×日付のマスから記事一覧を絞り込める。分野フィルタにも連動。
- PC・スマホ・ダーク表示で確認。スマホでは表を横スクロール。媒体一覧は開閉できる。

### 保存・数え方
- `config.yaml` の `media.publishers` に配信URLと媒体名。`fields` で専門媒体の分野を指定可能。
- `data/media.json` に見出し、日時、URL、媒体、取得状況、取得した日付範囲を保存。本文は保存しない。
- 公式RSSに掲載されていた範囲の件数であり、媒体の全記事を網羅するものではない。過去120日を遡って全件取れるわけでもない。
- Reutersは検索上限があり常に一部取得扱い。今日とフィードの最古日も一部取得。未取得日は0件にしない。
- 取得失敗時も保存済みの記事・取得範囲を保持。画面でエラー状態と保存分を表示。
- 媒体だけの履歴でHN等も取得済みと誤認しないよう、RSSの過去記事は専用の保存ファイルから発見処理に渡す。
- 新語発見では同一URLとRSSに重なるHN/GDELTの同一見出しを重複除外。新規収集のHN/GDELTにも記事URLを保持。
- 同一媒体・同日・同一見出しの別URLも重複保存しない。別媒体の同じ見出しは各媒体の掲載として数える。
- 従来のグラフにも「指定媒体の見出し」を追加。他ソースとの重複があるため英語圏合計には足さない。
- 指定媒体の色分け表は当日を含む。従来の追跡グラフは昨日まで。`count: None` は未取得、`partial: True` は一部取得。

### 検証
- `python -m pytest`: 40件成功（外部通信なし）。
- RSS/Atom、UTC変換、未来日付、不正な項目、途中失敗、前回データ保持、未知と0件の区別、重複排除を検証。
- `python -m trendwatch discover` と `python -m trendwatch build` を実行済み。
- ChromiumでPC・スマホ・ダーク表示、言葉/期間/分野切り替え、日付マスからの記事一覧表示と解除を確認。JavaScriptエラーとページの横はみ出しなし。
- 見出しの公開配信の接続確認は `python scripts/check_media_feeds.py`（ネット接続するのでpytestでは実行しない）。
