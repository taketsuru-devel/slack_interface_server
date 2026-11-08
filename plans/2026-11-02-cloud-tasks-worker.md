# ハンドラー呼び出しを Cloud Tasks 経由の別リクエストに分離する

## 背景

2026-10-31・11-02 に、Slack の「考え中...」が回答に更新されない事象が出た。ログを追うと次の流れだった。

- `slack-interface-server` は ack を返したあと、Bolt のバックグラウンドスレッドでハンドラーを呼んでいる（同期で 49〜185 秒かかる）
- ack の約 10 秒後に 2 つ目のインスタンスが起動した（`maxScale=1` なので 1 つ目と入れ替わったとみられる）
- `kakeibo-adk-agent` は 200 を返したが、Slack サーバー側には以降のログが一切なく、`chat_update` も実行されていない

Cloud Run は処理中のリクエストがないインスタンスを止めてよい。そのため、レスポンスを返したあとのスレッドが最後まで動く保証はない。

## 方針

ack 経路とハンドラー呼び出し経路を分ける。

```
Slack ─(event)→ POST /slack/events
                  ├ 「考え中...」を投稿
                  └ Cloud Tasks に {event, placeholder_ts} を積む → ack
Cloud Tasks ─(OIDC)→ POST /tasks/handle   ← 処理中はリクエストが開いたまま
                  ├ スレッド履歴取得・ルーティング・画像ダウンロード
                  ├ call_handler（最大 300 秒）
                  └ chat_update（失敗時はエラー文で更新）
```

- **Cloud Tasks を選ぶ理由**: HTTP ターゲットの dispatch deadline は最大 30 分（Pub/Sub push は最大 600 秒）。キュー単位で再試行回数を絞れる
- **再試行しない（`max_attempts = 1`）**: ハンドラーには `remember_fact` のような書き込み系もあるため、二重に実行しない。失敗したらプレースホルダーをエラー文に更新して終わる
- **タスク本文は event と placeholder_ts だけにする**: 画像の base64 はタスク上限の 1MB を超えうるので、ダウンロードはワーカー側で行う
- **`/tasks/handle` は自前で OIDC を検証する**: サービスは Slack 向けに `allUsers` 公開なので、Cloud Run の IAM には頼れない。`google.oauth2.id_token.verify_oauth2_token` で audience と `email`（= タスク用 SA）を照合する
- **ローカル（Socket Mode）はそのまま動かす**: `TASKS_QUEUE` が未設定なら、ワーカー関数を今と同じくリスナー内でインライン実行する。本番でも、env を外せば旧挙動に戻せる（ロールバック手段）
- **残るリスク**: プレースホルダー投稿とタスク投入は ack 後のスレッドで行う。ここは 1 秒未満なので許容する（今回の事象は 50 秒の間に起きた）

## 変更対象

| リポ | ファイル | 内容 |
|---|---|---|
| slack_interface_server | `app.py` | リスナーを「投稿＋投入」に縮め、`/tasks/handle` を追加 |
| slack_interface_server | `worker.py`（新規） | `process_mention(event, placeholder_ts, client)`：履歴取得〜`chat_update`、例外時はエラー文で更新 |
| slack_interface_server | `task_queue.py`（新規） | `enqueue(payload)`（google-cloud-tasks）・`verify_task_request(headers)`（google-auth） |
| slack_interface_server | `pyproject.toml` / `uv.lock` / `Dockerfile` | 依存追加、COPY に新ファイルを追加 |
| slack_interface_server | `tests/test_worker.py`・`tests/test_task_queue.py` | 下記の完了基準 |
| slack_interface_server | `CLAUDE.md`・`README.md`・`slack-server-spec.md` | アーキテクチャ図と環境変数（30 秒表記も 300 秒に直す） |
| infra | `gcp/slack_interface_server.tf` | API 有効化・キュー・IAM・env・`timeout = "600s"` |

## Task 0: 設計確認（実装前に済ませる）

- Context7 で google-cloud-tasks の `CloudTasksClient.create_task`（`http_request.oidc_token`・`dispatch_deadline`）と google-auth の `verify_oauth2_token` の現行シグネチャを確認する
- Cloud Tasks の OIDC トークンに入る claim（`email`・`aud`）を確認する
- `gcloud projects describe` でプロジェクト番号を取り、サービス URL を `https://slack-interface-server-<番号>.asia-northeast1.run.app` に決める（Terraform で自分自身の URI を env に入れると循環参照になるため）

## Task 1: ワーカー関数の切り出し（挙動は変えない）

1. 履歴取得から `chat_update` までを `worker.process_mention` に移す。リスナーはプレースホルダーを投稿してからこの関数を直接呼ぶ
2. 例外時は `chat_update` で「エラーが発生しました: <例外の型>」に更新し、例外をログに出す
3. `tests/test_worker.py`：Slack client と `call_handler` をフェイクに差し替え、(a) 正常時は回答で更新、(b) ハンドラー例外時はエラー文で更新、を確認する
4. `uv run pytest` と `uv run ruff check` が通ることを確認してコミットする

## Task 2: Cloud Tasks 経路

1. 依存追加：`uv add google-cloud-tasks google-auth`
2. `task_queue.enqueue(payload)`：`TASKS_QUEUE`（キューのフルパス）、`TASKS_SERVICE_URL`、`TASKS_SERVICE_ACCOUNT` を env から読む。宛先は `POST {url}/tasks/handle`、audience は `{url}`、`dispatch_deadline` は 600 秒
3. `task_queue.verify_task_request(headers)`：Bearer トークンを検証し、audience と `email` が一致しなければ `False` を返す
4. `app.py`：リスナーは `TASKS_QUEUE` があれば投入、なければ `process_mention` をインラインで呼ぶ。`/tasks/handle` は検証失敗で 403、成功なら `process_mention` を実行して 200 を返す（`process_mention` が例外を握るので常に 200 で、再試行もさせない）
5. `tests/test_task_queue.py`：(a) 投入するタスクの URL・OIDC・本文、(b) 検証で audience 違い・email 違いを弾く（`verify_oauth2_token` はモンキーパッチ）、(c) `/tasks/handle` は検証失敗で 403、を確認する
6. Dockerfile の COPY に `worker.py task_queue.py` を足し、pytest・ruff を通してコミットする

## Task 3: ドキュメント

`CLAUDE.md`・`README.md`・`slack-server-spec.md` のアーキテクチャ図・環境変数・タイムアウト表記を更新してコミットする。

## Task 4: infra（`infra` リポで別ブランチ）

`gcp/slack_interface_server.tf` に以下を追加する。

- `google_project_service` で `cloudtasks.googleapis.com` を有効化
- `google_cloud_tasks_queue "slack_handler"`（asia-northeast1、`retry_config { max_attempts = 1 }`）
- IAM
  - キューに対する `roles/cloudtasks.enqueuer`（slack_server SA）
  - SA 自身への `roles/iam.serviceAccountUser`（OIDC トークンを付けたタスクを作るのに actAs が要る）
- Cloud Run の env に `TASKS_QUEUE`・`TASKS_SERVICE_URL`・`TASKS_SERVICE_ACCOUNT` を追加し、`timeout = "600s"` を設定する

`terraform plan` で差分がこれだけであることを確認する。

## Task 5: デプロイと検証

順序：infra を先に apply する（旧コードは env を読まないので無害）→ `make push` → `gcloud run deploy slack-interface-server --image <IMAGE_URI> --region asia-northeast1`

完了基準：

- [x] pytest・ruff が全件通る
- [x] Slack の kakeibo チャンネルで、コールドスタート状態から 40 秒以上かかる質問をして回答に更新される
- [x] そのときのログで、`/slack/events` が数秒で終わり、`/tasks/handle` のリクエストがハンドラーの応答まで開いていることを確認する
- [x] Bearer なしで `/tasks/handle` を叩くと 403 になる
- [x] receipt チャンネルの画像付き投稿も従来どおり処理される

ロールバック：Cloud Run から `TASKS_QUEUE` を外せばインライン実行に戻る。
