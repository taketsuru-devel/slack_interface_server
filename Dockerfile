FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 依存関係を先にインストール（キャッシュ活用）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app.py router.py handler_client.py config.yaml ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=8080

CMD ["python", "app.py"]
