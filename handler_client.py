import os

import httpx

TIMEOUT = 30.0
METADATA_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"


def _get_id_token(audience: str) -> str | None:
    """Cloud Run 上でのみ Identity Token を取得する（ローカルでは None を返す）"""
    if not os.environ.get("K_SERVICE"):
        return None
    try:
        resp = httpx.get(
            METADATA_URL,
            params={"audience": audience},
            headers={"Metadata-Flavor": "Google"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[WARN] Failed to get identity token: {e}")
        return None


def call_handler(
    url: str,
    question: str,
    thread_history: list[dict],
    user_id: str,
    channel_id: str,
) -> str:
    payload = {
        "question": question,
        "thread_history": thread_history,
        "user_id": user_id,
        "channel_id": channel_id,
    }
    headers = {}
    token = _get_id_token(audience=url)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.post(f"{url}/query", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()["answer"]
