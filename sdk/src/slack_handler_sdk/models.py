from dataclasses import dataclass


@dataclass(frozen=True)
class HandlerRequest:
    """POST /query リクエストボディ."""

    question: str
    thread_history: list[dict[str, str]]
    user_id: str
    channel_id: str
