import pytest

import worker

EVENT = {"channel": "C1", "ts": "100.0", "user": "U1", "text": "<@B1> 今月は？"}


class FakeClient:
    """Slack WebClient の代わりに chat_update の呼び出しを記録する."""

    def __init__(self):
        self.updates: list[dict] = []

    def conversations_replies(self, channel, ts):
        return {
            "messages": [
                {"user": "U1", "text": "前の質問"},
                {"user": "B1", "text": "前の回答"},
                {"user": "U1", "text": "今月は？"},
            ]
        }

    def conversations_info(self, channel):
        return {"channel": {"name": "kakeibo"}}

    def chat_update(self, **kwargs):
        self.updates.append(kwargs)


@pytest.fixture
def fake_route(monkeypatch):
    monkeypatch.setattr(worker, "route", lambda channel_name, question: "https://handler")
    monkeypatch.setattr(worker, "extract_image_files", lambda event, token: [])


def test_updates_placeholder_with_answer(monkeypatch, fake_route):
    calls = []

    def fake_call_handler(url, **kwargs):
        calls.append((url, kwargs))
        return "残り3,200円です"

    monkeypatch.setattr(worker, "call_handler", fake_call_handler)
    client = FakeClient()

    worker.process_mention(
        EVENT,
        question="今月は？",
        placeholder_ts="101.0",
        client=client,
        bot_user_id="B1",
        token="t",
    )

    url, kwargs = calls[0]
    assert url == "https://handler"
    assert kwargs["thread_history"] == [
        {"role": "user", "content": "前の質問"},
        {"role": "assistant", "content": "前の回答"},
    ]
    assert client.updates == [{"channel": "C1", "ts": "101.0", "text": "残り3,200円です"}]


def test_updates_placeholder_with_error_when_handler_fails(monkeypatch, fake_route):
    def failing_call_handler(url, **kwargs):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(worker, "call_handler", failing_call_handler)
    client = FakeClient()

    worker.process_mention(
        EVENT,
        question="今月は？",
        placeholder_ts="101.0",
        client=client,
        bot_user_id="B1",
        token="t",
    )

    assert client.updates == [
        {"channel": "C1", "ts": "101.0", "text": "エラーが発生しました: TimeoutError"}
    ]
