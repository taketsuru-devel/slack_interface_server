import os
import re

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from worker import process_mention

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

_bot_user_id: str | None = None


def get_bot_user_id() -> str:
    global _bot_user_id
    if _bot_user_id is None:
        _bot_user_id = app.client.auth_test()["user_id"]
    return _bot_user_id


def strip_mention(text: str) -> str:
    return re.sub(r"<@[A-Z0-9]+>", "", text).strip()


@app.event("app_mention")
def handle_mention(event, say, client):
    thread_ts = event.get("thread_ts", event["ts"])
    question = strip_mention(event["text"])

    # 即座に「考え中...」を投稿（Slack 3秒タイムアウト対策）
    placeholder = say(text="考え中...", thread_ts=thread_ts)

    process_mention(
        event,
        question=question,
        placeholder_ts=placeholder["ts"],
        client=client,
        bot_user_id=get_bot_user_id(),
        token=SLACK_BOT_TOKEN,
    )


flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    # Cold start 時、Cloud Run は元リクエストをキューに保持しつつ Slack が 3 秒でリトライを送る。
    # コンテナ起動後に両方が届くため、リトライ側を無視して二重処理を防ぐ。
    if request.headers.get("X-Slack-Retry-Num"):
        return {"ok": True}
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
