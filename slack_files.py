import base64
from collections.abc import Callable

import httpx

DOWNLOAD_TIMEOUT = 10.0


def extract_image_files(
    event: dict,
    token: str,
    http_get: Callable[..., httpx.Response] = httpx.get,
) -> list[dict[str, str]]:
    """イベントの添付ファイルのうち画像だけを bot トークンでダウンロードし、base64 で返す.

    返り値の各要素は ``{"name", "mimetype", "data_base64"}``。画像がなければ空リスト。
    """
    images = []
    for f in event.get("files", []):
        mimetype = f.get("mimetype", "")
        if not mimetype.startswith("image/"):
            continue
        resp = http_get(
            f["url_private"],
            headers={"Authorization": f"Bearer {token}"},
            timeout=DOWNLOAD_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        images.append(
            {
                "name": f.get("name", ""),
                "mimetype": mimetype,
                "data_base64": base64.b64encode(resp.content).decode(),
            }
        )
    return images
