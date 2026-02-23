import os

import yaml

_config = None


def _load_config() -> dict:
    global _config
    if _config is None:
        config_path = os.environ.get("HANDLER_CONFIG_PATH", "./config.yaml")
        with open(config_path) as f:
            _config = yaml.safe_load(f)
    return _config


def route(channel_name: str, question: str) -> str:
    """ルーティング優先順位: channel → keyword → default"""
    config = _load_config()
    handlers = config.get("handlers", [])

    default_url = None

    for handler in handlers:
        trigger = handler["trigger"]
        trigger_type = trigger["type"]

        if trigger_type == "default":
            default_url = handler["url"]
        elif trigger_type == "channel":
            if trigger.get("value") == channel_name:
                return handler["url"]
        elif trigger_type == "keyword":
            if trigger.get("value", "") in question:
                return handler["url"]

    if default_url:
        return default_url

    raise ValueError(f"No handler found for channel={channel_name!r}, question={question!r}")
