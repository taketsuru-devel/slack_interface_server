import os
import re

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from handler_client import call_handler
from router import route

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


def get_channel_name(client, channel_id: str) -> str:
    try:
        result = client.conversations_info(channel=channel_id)
        return result["channel"]["name"]
    except Exception as e:
        print(f"[WARN] conversations_info failed for {channel_id}: {e}")
        return ""


def build_history(replies: dict, bot_user_id: str) -> list[dict]:
    """今回の発言を除いた過去の会話履歴を構築する（古い順）"""
    history = []
    for msg in replies["messages"][:-1]:
        role = "assistant" if msg.get("user") == bot_user_id else "user"
        history.append({"role": role, "content": msg["text"]})
    return history


@app.event("app_mention")
def handle_mention(event, say, client):
    channel = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    question = strip_mention(event["text"])

    # 即座に「考え中...」を投稿（Slack 3秒タイムアウト対策）
    placeholder = say(text="考え中...", thread_ts=thread_ts)

    # スレッド履歴取得
    replies = client.conversations_replies(channel=channel, ts=thread_ts)
    thread_history = build_history(replies, bot_user_id=get_bot_user_id())

    # ルーティング
    channel_name = get_channel_name(client, channel)
    handler_url = route(channel_name=channel_name, question=question)

    # ハンドラー呼び出し
    answer = call_handler(
        handler_url,
        question=question,
        thread_history=thread_history,
        user_id=event["user"],
        channel_id=channel,
    )

    # 返答で更新
    client.chat_update(channel=channel, ts=placeholder["ts"], text=answer)


flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
