FROM python:3.14-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# ── Parser (one-shot) ────────────────────────────────────────────
FROM base AS parser
ENTRYPOINT ["uv", "run", "mosaic"]

# ── MCP Server ───────────────────────────────────────────────────
FROM base AS mcp
EXPOSE 8080
ENV MOSAIC_DB=/data/health.duckdb
CMD ["uv", "run", "python", "-c", \
     "from mosaic.server import mcp; mcp.run(transport='http', host='0.0.0.0', port=8080)"]
