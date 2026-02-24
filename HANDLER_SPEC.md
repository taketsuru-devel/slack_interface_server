# Slack Interface Server — ハンドラー実装仕様

このドキュメントは `slack-interface-server` からリクエストを受け取るハンドラーサービスの実装仕様を定義する。

## 概要

ハンドラーは Slack SDK を持たない純粋な HTTP API サーバー。
`slack-interface-server` が Slack I/O を一手に担い、ハンドラーはビジネスロジックのみに集中する。

```
Slack (app_mention)
  ↓
slack-interface-server   # Slack 認証・スレッド履歴取得・ルーティング・返信
  ↓  POST /query
ハンドラー（このリポジトリ）  # ビジネスロジックのみ
```

---

## エンドポイント仕様

### `POST /query`

#### Request

```
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

| フィールド | 型 | 説明 |
|---|---|---|
| `question` | string | 今回のユーザー発言（メンション除去済み） |
| `thread_history` | array | 今回の発言を除いた過去の会話履歴（古い順）。新規スレッドは `[]` |
| `user_id` | string | 発言したユーザーの Slack UID |
| `channel_id` | string | 発言があったチャンネルの Slack ID |

#### Response

```json
{
  "answer": "残り3,200円です（予算8,000円 − 使用4,800円）"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `answer` | string | Slack スレッドに返信するテキスト |

- HTTP 200 を返すこと
- タイムアウトは **30秒以内**に応答すること（slack-interface-server 側の設定値）

---

## 実装例（SDK 利用 — 推奨）

`slack-handler-sdk` を使うと、エンドポイント定義やリクエストパースを省略できる。

```bash
pip install "slack-handler-sdk @ git+https://github.com/taketsuru-devel/slack_interface_server.git@main#subdirectory=sdk"
```

```python
from slack_handler_sdk import HandlerRequest, create_handler_app, run_app

def handle(req: HandlerRequest) -> str:
    # req.question, req.thread_history, req.user_id, req.channel_id が利用可能
    return "ビジネスロジックの結果"

app = create_handler_app(handle)

if __name__ == "__main__":
    run_app(app)
```

SDK が `/query`（POST）と `/health`（GET）を自動登録する。ハンドラーは `handler_fn` の実装だけに集中すればよい。

## 実装例（素の Flask）

SDK を使わない場合は以下のように直接実装する。

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/query", methods=["POST"])
def query():
    body = request.get_json()
    question = body["question"]
    thread_history = body["thread_history"]  # list of {"role": ..., "content": ...}
    user_id = body["user_id"]
    channel_id = body["channel_id"]

    # ビジネスロジックをここに実装
    answer = handle(question, thread_history)

    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```

---

## ローカルテスト

```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "テスト",
    "thread_history": [],
    "user_id": "U12345678",
    "channel_id": "C12345678"
  }'
```

---

## slack-interface-server への登録

ハンドラーをデプロイしたら、`slack-interface-server` リポジトリの `config.yaml` にエントリを追加する。

```yaml
handlers:
  - name: your-handler
    trigger:
      type: channel      # channel / keyword / default のいずれか
      value: "チャンネル名"
    url: https://your-handler-xxxx.run.app
```

### トリガー種別

| type | value | マッチ条件 |
|---|---|---|
| `channel` | チャンネル名 | 特定チャンネルでのメンション |
| `keyword` | キーワード文字列 | 発言テキストにキーワードを含む |
| `default` | （不要） | どのトリガーにもマッチしなかった場合 |

優先順位: `channel` → `keyword` → `default`

### IAM 設定（プライベート Cloud Run の場合）

ハンドラーをプライベート Cloud Run としてデプロイする場合、`infra` リポジトリの Terraform で `roles/run.invoker` を付与すること。

```hcl
# infra/gcp/ に追加
resource "google_cloud_run_v2_service_iam_member" "slack_invoker" {
  name     = google_cloud_run_v2_service.handler.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.slack_server.email}"
}
```
