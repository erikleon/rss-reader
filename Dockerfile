# syntax=docker/dockerfile:1

# --- Stage 1: build the Svelte frontend ---
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime (API + built frontend) ---
FROM python:3.12-slim
WORKDIR /app

# Editable install so backend/migrations resolves at runtime (init_db locates
# the Alembic scripts relative to the package source).
COPY pyproject.toml README.md alembic.ini ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir -e .

# Serve the built frontend from FastAPI's static mount.
COPY --from=frontend /app/frontend/dist ./frontend/dist

ENV RSS_READER_DB=/data/rss_reader.db
VOLUME ["/data"]
# Port is configurable via the RSS_READER_PORT env var (read by the serve command).
EXPOSE ${RSS_READER_PORT:-8000}

CMD ["rss-reader", "serve", "--host", "0.0.0.0"]
