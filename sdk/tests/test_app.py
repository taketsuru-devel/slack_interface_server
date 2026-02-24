import json

import pytest

from slack_handler_sdk import HandlerRequest, create_handler_app


def _echo_handler(req: HandlerRequest) -> str:
    return f"echo: {req.question}"


@pytest.fixture()
def client():
    app = create_handler_app(_echo_handler)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestHealth:
    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}


class TestQuery:
    def test_basic_query(self, client):
        resp = client.post(
            "/query",
            json={
                "question": "hello",
                "thread_history": [],
                "user_id": "U123",
                "channel_id": "C123",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"answer": "echo: hello"}

    def test_minimal_fields(self, client):
        """question のみでも動作する（user_id, channel_id はオプショナル）."""
        resp = client.post("/query", json={"question": "test"})
        assert resp.status_code == 200
        assert resp.get_json()["answer"] == "echo: test"

    def test_missing_question_returns_400(self, client):
        resp = client.post("/query", json={"thread_history": []})
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/query",
            data="not json",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_thread_history_passed(self, client):
        history = [{"role": "user", "content": "hi"}]
        captured = {}

        def capture_handler(req: HandlerRequest) -> str:
            captured["req"] = req
            return "ok"

        app = create_handler_app(capture_handler)
        app.config["TESTING"] = True
        with app.test_client() as c:
            c.post(
                "/query",
                json={
                    "question": "q",
                    "thread_history": history,
                    "user_id": "U1",
                    "channel_id": "C1",
                },
            )

        assert captured["req"].thread_history == history
        assert captured["req"].user_id == "U1"
        assert captured["req"].channel_id == "C1"
