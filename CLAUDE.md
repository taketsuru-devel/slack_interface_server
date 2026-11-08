# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

複数プロジェクトで共用できる Slack Bot サーバー。Slack Event API を受け取り、`config.yaml` のルーティング設定に従って各プロジェクトのハンドラーへ HTTP POST する。

詳細仕様: `slack-server-spec.md`

## 技術スタック

- Python 3.13
- Slack Bolt for Python + Flask（Event API受信・ack自動処理）
- httpx（ハンドラー呼び出し）
- PyYAML（config.yaml 読み込み）
- Terraform（GCP リソース管理 → `infra/` リポジトリに移行済み）

## コマンド

```bash
# ローカル開発（Socket Mode、ngrok不要）
make up         # python local_dev.py を起動

# Docker ビルド・デプロイ（linux/amd64 必須: M1 Mac 対応）
make build      # docker buildx build --platform linux/amd64
make push       # build + docker push

# Terraform（infra/ リポジトリで管理）
cd ../infra/gcp && terraform plan
cd ../infra/gcp && terraform apply
```

## アーキテクチャ

```
Slack (app_mention)
  ↓
app.py            # /slack/events: 「考え中...」を投稿し Cloud Tasks に積んで ack
  ↓  Cloud Tasks (OIDC, 再試行なし)
app.py            # /tasks/handle: OIDC を検証して worker を呼ぶ
  ↓
worker.py         # 履歴取得・ルーティング・画像取得・ハンドラー呼び出し・chat_update
  ├ router.py         # config.yaml 読み込み・ルーティング (channel → keyword → default)
  └ handler_client.py # POST /query to handler (httpx, 300秒タイムアウト)
  ↓
各ハンドラー (別リポジトリ)
```

**Slack 3秒タイムアウト対策**: `app_mention` 受信後、即座に「考え中...」を投稿し、ハンドラーレスポンス後に `chat_update` で上書きする。失敗時はエラー文で上書きする。

**Cloud Tasks を挟む理由**: Cloud Run は処理中のリクエストがないインスタンスを止めてよいため、ack 後のスレッドでハンドラーを待つと回答が消えることがある（2026-10-31・11-02 に発生）。`/tasks/handle` のリクエストの中で待つ。`TASKS_QUEUE` が未設定ならリスナー内でその場で処理する（ローカルの Socket Mode、本番のロールバック用）。`/tasks/handle` はサービスが `allUsers` 公開なので、アプリ側で OIDC トークンの audience と email を検証する。

## ハンドラー通信インターフェース

```
POST /query
{ "question": str, "thread_history": [...], "user_id": str, "channel_id": str, "files": [{"name", "mimetype", "data_base64"}] }
→ { "answer": str }
```

## GCP 環境

- Project ID: `<PROJECT_ID>`（`../infra/gcp` で `terraform output -raw project_id`）
- Region: `asia-northeast1`（東京）
- Cloud Run: `slack-interface-server`（min=0, max=1, `startup_cpu_boost=true` 必須）
- Artifact Registry: `asia-northeast1-docker.pkg.dev/<PROJECT_ID>/slack-interface-server/app:latest`
- Secret Manager: `slack-bot-token`, `slack-signing-secret`

## 環境変数

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...   # Socket Mode用（ローカルのみ）
HANDLER_CONFIG_PATH=./config.yaml
# 本番のみ（infra で設定）。未設定ならハンドラーをその場で呼ぶ
TASKS_QUEUE=projects/<PROJECT_ID>/locations/asia-northeast1/queues/slack-handler
TASKS_SERVICE_URL=https://slack-interface-server-<PROJECT_NUMBER>.asia-northeast1.run.app
TASKS_SERVICE_ACCOUNT=slack-interface-server@<PROJECT_ID>.iam.gserviceaccount.com
```

`config.yaml` は Cloud Run URL を含むため git 管理外。`config.example.yaml` をコピーして実 URL を入れる（`make build` 時にイメージへ同梱される）。

## 運用メモ

`latest` タグはデプロイ時点の SHA に固定される。ARの最新と一致しているか確認するには：

```bash
REVISION=$(gcloud run services describe slack-interface-server --region asia-northeast1 --project <PROJECT_ID> --format="value(status.latestReadyRevisionName)")
gcloud run revisions describe $REVISION --region asia-northeast1 --project <PROJECT_ID> --format="value(spec.containers[0].image)"
# sha256:... をAR側の digest と比較する
```

## 実装順序

1. `infra/gcp/slack_interface_server.tf` - Cloud Run / AR / Secret Manager（`infra/` リポ）
2. `app.py` + `router.py` + `handler_client.py`
3. `Dockerfile` + `requirements.txt` + `Makefile`
4. `terraform apply`（`infra/gcp/`）→ Cloud Run URL → Slack App Event Subscriptions に設定
5. Socket Mode でローカル確認 → Cloud Run でエンドツーエンド確認
