from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from flask import Flask, jsonify, request

from .models import HandlerRequest


def create_handler_app(handler_fn: Callable[[HandlerRequest], str]) -> Flask:
    """Flask アプリを生成する。

    ``/query`` と ``/health`` エンドポイントを登録し、
    リクエストのパース・バリデーション・エラーハンドリングを行う。

    Args:
        handler_fn: ``HandlerRequest`` を受け取り回答文字列を返す関数。
    """
    app = Flask(__name__)

    @app.route("/query", methods=["POST"])
    def query() -> tuple[Any, int]:
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "invalid JSON"}), 400

        try:
            req = HandlerRequest(
                question=body["question"],
                thread_history=body.get("thread_history", []),
                user_id=body.get("user_id", ""),
                channel_id=body.get("channel_id", ""),
            )
        except (KeyError, TypeError) as e:
            return jsonify({"error": f"missing field: {e}"}), 400

        answer = handler_fn(req)
        return jsonify({"answer": answer}), 200

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Any, int]:
        return jsonify({"status": "ok"}), 200

    return app


def run_app(app: Flask) -> None:
    """Cloud Run 向けにアプリを起動する。"""
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
