# 汎用 Slack サーバー 実装仕様書

## 目的

複数プロジェクトで共用できる Slack Bot サーバーを新規リポジトリとして実装する。
各プロジェクトはプロジェクト固有の「ハンドラー」を持ち、この共用サーバーが Slack I/O を一手に担う。

---

## アーキテクチャ

```
Slack
  ↓ Event API (app_mention)
┌─────────────────────────────────────┐
│  shared-slack-server (このリポジトリ) │
│  ・Slack 認証・Event 受信            │
│  ・スレッド履歴取得                  │
│  ・ルーティング (config.yaml)        │
│  ・Slack への返信                    │
└──────────┬──────────────────────────┘
           │ HTTP POST /query
    { question, thread_history, user_id }
           │
    ┌──────┴──────────────────┐
    ↓                         ↓
kakeibo-handler           other-handler  （将来追加）
（別リポジトリ）           （別リポジトリ）
    ↓
{ answer: "3,200円です" }
    ↓
shared-slack-server → Slack スレッド返信
```

**設計原則:**
- この共用サーバーは Slack トークン・Signing Secret のみ保持
- ハンドラーは Slack SDK を持たない純粋な HTTP API
- ハンドラーの URL は `config.yaml` で管理

---

## ハンドラーとの通信インターフェース（固定仕様）

ハンドラーは以下の仕様を満たす HTTP サーバーであること。

### Request

```
POST /query
Content-Type: application/json
```

```json
{
  "question": "今月の外食費の残りは？",
  "thread_history": [
    {"role": "user",      "content": "先月の外食費は？"},
    {"role": "assistant", "content": "先月は4,500円でした"}
  ],
  "user_id": "U12345678",
  "channel_id": "C12345678"
}
```

- `thread_history`: 今回の発言を除いた過去の会話履歴（古い順）。新規スレッドの場合は空配列 `[]`
- `question`: 今回のユーザー発言（メンション除去済み）

### Response

```json
{
  "answer": "残り3,200円です（予算8,000円 − 使用4,800円）"
}
```

- HTTP 200 を返すこと
- タイムアウトは 30 秒を想定（shared-server 側のタイムアウト設定）

---

## ルーティング設定 (config.yaml)

```yaml
handlers:
  - name: kakeibo
    trigger:
      type: channel        # channel / keyword / default
      value: "家計簿"       # チャンネル名
    url: https://kakeibo-handler-xxxx.run.app

  - name: fallback
    trigger:
      type: default
    url: https://other-handler-xxxx.run.app
```

ルーティング優先順位: `channel` → `keyword` → `default`

---

## 技術スタック

| 項目 | 選定 | 理由 |
|------|------|------|
| 言語 | Python 3.12 | Slack Bolt が Python 公式対応 |
| フレームワーク | Slack Bolt for Python + Flask | Event API・ack() 自動処理 |
| HTTP クライアント | httpx | async 対応、ハンドラー呼び出しに使用 |
| 設定管理 | PyYAML | config.yaml 読み込み |
| インフラ | Terraform | GCP リソース管理 |

---

## インフラ仕様（GCP）

### 既存 GCP 環境（接続先プロジェクト情報）

```
Project ID : followedwind-manage-test-3
Region     : asia-northeast1（東京）
```

### Cloud Run サービス

```terraform
resource "google_cloud_run_v2_service" "slack_server" {
  name     = "shared-slack-server"
  location = var.region

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/shared-slack-server/app:latest"
      resources {
        limits = { cpu = "1", memory = "256Mi" }
      }
      # Slack Token, Signing Secret は Secret Manager から注入（下記参照）
    }
    scaling {
      min_instance_count = 0   # スケールゼロ（コスト最小化）
      max_instance_count = 1
    }
    startup_cpu_boost = true   # コールドスタート短縮（重要）
  }
}
```

**`startup_cpu_boost = true` は必須。** Slack の 3 秒タイムアウトに対してコールドスタートを収めるため。

### Artifact Registry

```
リポジトリ名 : shared-slack-server
イメージURI  : asia-northeast1-docker.pkg.dev/followedwind-manage-test-3/shared-slack-server/app:latest
```

ビルドは M1 Mac 対応のため `docker buildx build --platform linux/amd64` を使用すること（既存プロジェクトの慣例）。

### Secret Manager（Slack App から取得する値）

| Secret ID | 内容 |
|-----------|------|
| `slack-bot-token` | `xoxb-...` Bot User OAuth Token |
| `slack-signing-secret` | Signing Secret |

### Service Account IAM

```
roles/secretmanager.secretAccessor  # Secret Manager 参照
roles/run.invoker                    # 各ハンドラー Cloud Run 呼び出し（必要な場合）
```

---

## ファイル構成

```
shared-slack-server/
├── app.py               # Slack Bolt + Flask エントリポイント
├── router.py            # config.yaml 読み込み・ルーティングロジック
├── handler_client.py    # ハンドラー HTTP 呼び出し（httpx）
├── config.yaml          # ルーティング設定（ハンドラー URL 一覧）
├── Dockerfile
├── requirements.txt
├── Makefile             # build / push / up（ローカル開発用）
├── .env.example         # ローカル開発用環境変数サンプル
└── terraform/
    ├── main.tf          # Cloud Run / AR / SA / Secret Manager
    ├── variables.tf
    └── outputs.tf       # Cloud Run URL 出力（Slack App 設定に使用）
```

---

## app.py 実装イメージ

```python
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from router import route
from handler_client import call_handler

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

@app.event("app_mention")
def handle_mention(event, say, client):
    channel    = event["channel"]
    thread_ts  = event.get("thread_ts", event["ts"])
    question   = strip_mention(event["text"])

    # 即座に「考え中...」を投稿（Slack 3秒タイムアウト対策）
    placeholder = say(text="考え中...", thread_ts=thread_ts)

    # スレッド履歴取得
    replies = client.conversations_replies(channel=channel, ts=thread_ts)
    thread_history = build_history(replies, bot_user_id=app.client.auth_test()["user_id"])

    # ルーティング
    handler_url = route(channel_name=get_channel_name(client, channel))

    # ハンドラー呼び出し
    answer = call_handler(handler_url, question, thread_history, event["user"])

    # 返答で更新
    client.chat_update(channel=channel, ts=placeholder["ts"], text=answer)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)
```

---

## Slack App 設定（手動作業）

1. https://api.slack.com/apps で新規 App 作成
2. **Event Subscriptions** を有効化
   - Request URL: `https://<Cloud Run URL>/slack/events`
   - Subscribe: `app_mention`
3. **OAuth & Permissions** → Bot Token Scopes:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history`
   - `groups:history`
4. ワークスペースにインストール
5. Bot Token と Signing Secret を Secret Manager に登録

---

## ローカル開発

Slack Bolt の **Socket Mode** を使うことで ngrok 不要でローカル開発可能。

```python
# local_dev.py
from slack_bolt.adapter.socket_mode import SocketModeHandler
SocketModeHandler(app, SLACK_APP_TOKEN).start()
```

`.env.example`:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...   # Socket Mode 用（ローカルのみ）
HANDLER_CONFIG_PATH=./config.yaml
```

---

## Makefile（既存プロジェクトの慣例に合わせること）

```makefile
PROJECT_ID := $(shell cd terraform && terraform output -raw project_id 2>/dev/null)
IMAGE_URI  := asia-northeast1-docker.pkg.dev/$(PROJECT_ID)/shared-slack-server/app:latest

.PHONY: up build push

up:   # Socket Mode でローカル起動
	python local_dev.py

build:
	docker buildx build --platform linux/amd64 -t $(IMAGE_URI) .

push: build
	gcloud auth configure-docker asia-northeast1-docker.pkg.dev
	docker push $(IMAGE_URI)
```

---

## 実装順序

1. `terraform/` - Cloud Run / AR / Secret Manager のリソース定義
2. `app.py` + `router.py` + `handler_client.py` - コアロジック
3. `Dockerfile` + `requirements.txt`
4. `Makefile`
5. `terraform apply` → Cloud Run URL 取得 → Slack App の Event Subscriptions に設定
6. ローカルで Socket Mode 動作確認 → Cloud Run でエンドツーエンド確認

---

## 備考

- ハンドラー側（例: kakeibo）の実装仕様は各プロジェクトのリポジトリを参照
- kakeibo ハンドラーは `dbt_kakeibo` リポジトリの `slack_handler/` ディレクトリに実装予定
- config.yaml のハンドラー URL はデプロイ後に各プロジェクトの Cloud Run URL を記入する
