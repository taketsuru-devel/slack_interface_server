import traceback

from handler_client import call_handler
from router import route
from slack_files import extract_image_files


def build_history(replies: dict, bot_user_id: str) -> list[dict]:
    """今回の発言を除いた過去の会話履歴を構築する（古い順）"""
    history = []
    for msg in replies["messages"][:-1]:
        role = "assistant" if msg.get("user") == bot_user_id else "user"
        history.append({"role": role, "content": msg["text"]})
    return history


def get_channel_name(client, channel_id: str) -> str:
    try:
        result = client.conversations_info(channel=channel_id)
        return result["channel"]["name"]
    except Exception as e:
        print(f"[WARN] conversations_info failed for {channel_id}: {e}")
        return ""


def process_mention(
    event: dict,
    question: str,
    placeholder_ts: str,
    client,
    bot_user_id: str,
    token: str,
) -> None:
    """ハンドラーを呼び、「考え中...」を回答で更新する。失敗時はエラー文で更新して例外を握る"""
    channel = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    try:
        # スレッド履歴取得
        replies = client.conversations_replies(channel=channel, ts=thread_ts)
        thread_history = build_history(replies, bot_user_id=bot_user_id)

        # ルーティング
        channel_name = get_channel_name(client, channel)
        handler_url = route(channel_name=channel_name, question=question)

        # 添付画像をダウンロード（ハンドラーは Slack トークンを持たないためここで取得する）
        files = extract_image_files(event, token=token)

        # ハンドラー呼び出し
        answer = call_handler(
            handler_url,
            question=question,
            thread_history=thread_history,
            user_id=event["user"],
            channel_id=channel,
            files=files,
        )
    except Exception as e:
        traceback.print_exc()
        answer = f"エラーが発生しました: {type(e).__name__}"

    # 返答で更新
    client.chat_update(channel=channel, ts=placeholder_ts, text=answer)
