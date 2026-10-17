import base64

import httpx

from slack_files import extract_image_files


class FakeGet:
    """httpx.get の代わりに呼び出しを記録し、URL ごとの本文を返す."""

    def __init__(self, contents: dict[str, bytes]):
        self.contents = contents
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, **kwargs) -> httpx.Response:
        self.calls.append((url, kwargs))
        return httpx.Response(200, content=self.contents[url], request=httpx.Request("GET", url))


def test_extracts_only_images():
    get = FakeGet({"https://files/r.jpg": b"jpeg-bytes", "https://files/a.pdf": b"pdf"})
    event = {
        "files": [
            {"name": "r.jpg", "mimetype": "image/jpeg", "url_private": "https://files/r.jpg"},
            {"name": "a.pdf", "mimetype": "application/pdf", "url_private": "https://files/a.pdf"},
        ]
    }

    result = extract_image_files(event, token="xoxb-1", http_get=get)

    assert result == [
        {
            "name": "r.jpg",
            "mimetype": "image/jpeg",
            "data_base64": base64.b64encode(b"jpeg-bytes").decode(),
        }
    ]
    assert [url for url, _ in get.calls] == ["https://files/r.jpg"]


def test_sends_bearer_token():
    get = FakeGet({"https://files/r.png": b"png"})
    event = {
        "files": [{"name": "r.png", "mimetype": "image/png", "url_private": "https://files/r.png"}]
    }

    extract_image_files(event, token="xoxb-secret", http_get=get)

    _, kwargs = get.calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer xoxb-secret"


def test_no_files_returns_empty():
    get = FakeGet({})
    assert extract_image_files({"text": "hi"}, token="xoxb-1", http_get=get) == []
    assert get.calls == []
