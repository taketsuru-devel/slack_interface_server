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
app.py            # Slack Bolt + Flask エントリポイント (/slack/events)
  ↓
router.py         # config.yaml 読み込み・ルーティング (channel → keyword → default)
  ↓
handler_client.py # POST /query to handler (httpx, 30秒タイムアウト)
  ↓
各ハンドラー (別リポジトリ)
```

**Slack 3秒タイムアウト対策**: `app_mention` 受信後、即座に「考え中...」を投稿し、ハンドラーレスポンス後に `chat_update` で上書きする。

## ハンドラー通信インターフェース

```
POST /query
{ "question": str, "thread_history": [...], "user_id": str, "channel_id": str }
→ { "answer": str }
```

## GCP 環境

- Project ID: `followedwind-manage-test-3`
- Region: `asia-northeast1`（東京）
- Cloud Run: `slack-interface-server`（min=0, max=1, `startup_cpu_boost=true` 必須）
- Artifact Registry: `asia-northeast1-docker.pkg.dev/followedwind-manage-test-3/slack-interface-server/app:latest`
- Secret Manager: `slack-bot-token`, `slack-signing-secret`

## 環境変数

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...   # Socket Mode用（ローカルのみ）
HANDLER_CONFIG_PATH=./config.yaml
```

## 実装順序

1. `infra/gcp/slack_interface_server.tf` - Cloud Run / AR / Secret Manager（`infra/` リポ）
2. `app.py` + `router.py` + `handler_client.py`
3. `Dockerfile` + `requirements.txt` + `Makefile`
4. `terraform apply`（`infra/gcp/`）→ Cloud Run URL → Slack App Event Subscriptions に設定
5. Socket Mode でローカル確認 → Cloud Run でエンドツーエンド確認
