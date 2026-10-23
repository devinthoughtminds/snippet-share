FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Outside /app, so the dev bind mount of ./backend doesn't hide it.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --create-home app
USER app

EXPOSE 8000
# Migrate first, so a fresh database gets its tables before the app starts.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
