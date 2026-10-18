from dataclasses import dataclass, field


@dataclass(frozen=True)
class HandlerRequest:
    """POST /query リクエストボディ."""

    question: str
    thread_history: list[dict[str, str]]
    user_id: str
    channel_id: str
    # 添付画像。各要素は {"name", "mimetype", "data_base64"}。既存ハンドラー互換のため既定は空。
    files: list[dict[str, str]] = field(default_factory=list)
