FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# The lock installs the scanner package from ../mcp-secret-scanner, so keep that layout (compose passes it as the `scanner` context).
WORKDIR /src/mcp-server
COPY --from=scanner . /src/mcp-secret-scanner

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --create-home app
USER app

EXPOSE 8001
CMD ["python", "server.py"]
