# slack_interface_server

複数プロジェクトで共用できる Slack Bot サーバー。Slack Event API を受け取り、`config.yaml` のルーティング設定に従って各プロジェクトのハンドラーへ HTTP POST する。

## アーキテクチャ

```
Slack (app_mention)
  ↓
slack_interface_server   # Slack 認証・スレッド履歴取得・ルーティング・返信
  ↓  POST /query
各ハンドラーサービス（別リポジトリ）
```

## ハンドラーの実装

新しいハンドラーを実装する場合は以下を参照:

**[HANDLER_SPEC.md](./HANDLER_SPEC.md)** — ハンドラー実装仕様（POST /query インターフェース・登録手順）

## GCP 環境

- Cloud Run: `slack-interface-server`（asia-northeast1）
- Project: `followedwind-manage-test-3`
