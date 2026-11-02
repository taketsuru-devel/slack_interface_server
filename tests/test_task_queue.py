import json

import pytest

import task_queue

SERVICE_URL = "https://slack-interface-server.example.run.app"
SA = "slack-interface-server@proj.iam.gserviceaccount.com"


@pytest.fixture(autouse=True)
def tasks_env(monkeypatch):
    monkeypatch.setenv("TASKS_QUEUE", "projects/p/locations/asia-northeast1/queues/q")
    monkeypatch.setenv("TASKS_SERVICE_URL", SERVICE_URL)
    monkeypatch.setenv("TASKS_SERVICE_ACCOUNT", SA)


def test_build_task_targets_task_path_with_oidc():
    payload = {"event": {"channel": "C1"}, "question": "今月は？", "placeholder_ts": "101.0"}

    task = task_queue.build_task(payload)

    req = task.http_request
    assert req.url == f"{SERVICE_URL}/tasks/handle"
    assert req.oidc_token.service_account_email == SA
    assert req.oidc_token.audience == SERVICE_URL
    assert json.loads(req.body) == payload
    assert task.dispatch_deadline.seconds == 600


@pytest.fixture
def fake_verify(monkeypatch):
    seen = {}

    def set_claims(claims):
        def verify(token, request, audience):
            seen["audience"] = audience
            return claims

        monkeypatch.setattr(task_queue.id_token, "verify_oauth2_token", verify)
        return seen

    return set_claims


def test_verify_accepts_task_service_account(fake_verify):
    seen = fake_verify({"email": SA, "email_verified": True})

    assert task_queue.verify_task_request("Bearer tok") is True
    assert seen["audience"] == SERVICE_URL


def test_verify_rejects_other_service_account(fake_verify):
    fake_verify({"email": "other@proj.iam.gserviceaccount.com", "email_verified": True})

    assert task_queue.verify_task_request("Bearer tok") is False


def test_verify_rejects_invalid_token(monkeypatch):
    def verify(token, request, audience):
        raise ValueError("Token has wrong audience")

    monkeypatch.setattr(task_queue.id_token, "verify_oauth2_token", verify)

    assert task_queue.verify_task_request("Bearer tok") is False


@pytest.mark.parametrize("header", [None, "", "Basic abc"])
def test_verify_rejects_missing_bearer(header):
    assert task_queue.verify_task_request(header) is False
