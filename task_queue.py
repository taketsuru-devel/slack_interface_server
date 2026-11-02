"""ハンドラー呼び出しを Cloud Tasks 経由の別リクエストにする.

Cloud Run はレスポンス後のスレッドを最後まで動かす保証がないため、
ack 後の長い処理は Cloud Tasks から /tasks/handle を呼ばせて、リクエストの中で行う。
"""

import json
import os

from google.auth.transport import requests as google_requests
from google.cloud import tasks_v2
from google.oauth2 import id_token
from google.protobuf import duration_pb2

TASK_PATH = "/tasks/handle"
# ハンドラーの 300 秒タイムアウト + 履歴取得・画像ダウンロード・chat_update の余裕
DISPATCH_DEADLINE_SECONDS = 600

_client: tasks_v2.CloudTasksClient | None = None


def enabled() -> bool:
    return bool(os.environ.get("TASKS_QUEUE"))


def _get_client() -> tasks_v2.CloudTasksClient:
    global _client
    if _client is None:
        _client = tasks_v2.CloudTasksClient()
    return _client


def build_task(payload: dict) -> tasks_v2.Task:
    service_url = os.environ["TASKS_SERVICE_URL"]
    return tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{service_url}{TASK_PATH}",
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload).encode(),
            oidc_token=tasks_v2.OidcToken(
                service_account_email=os.environ["TASKS_SERVICE_ACCOUNT"],
                audience=service_url,
            ),
        ),
        dispatch_deadline=duration_pb2.Duration(seconds=DISPATCH_DEADLINE_SECONDS),
    )


def enqueue(payload: dict) -> None:
    _get_client().create_task(parent=os.environ["TASKS_QUEUE"], task=build_task(payload))


def verify_task_request(authorization: str | None) -> bool:
    """Cloud Tasks が付けた OIDC トークンか検証する（サービスは allUsers 公開のため自前で行う）"""
    if not authorization or not authorization.startswith("Bearer "):
        return False
    try:
        claims = id_token.verify_oauth2_token(
            authorization.removeprefix("Bearer "),
            google_requests.Request(),
            audience=os.environ["TASKS_SERVICE_URL"],
        )
    except ValueError as e:
        print(f"[WARN] task token verification failed: {e}")
        return False
    return (
        claims.get("email") == os.environ["TASKS_SERVICE_ACCOUNT"]
        and claims.get("email_verified") is True
    )
