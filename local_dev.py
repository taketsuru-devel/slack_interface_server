"""Socket Mode でローカル開発起動（ngrok 不要）"""
import os

from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

from app import app  # noqa: E402 （load_dotenv の後に import する必要がある）

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
