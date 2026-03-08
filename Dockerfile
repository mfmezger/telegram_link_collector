FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home appuser && mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser

ENV SQLITE_PATH=/data/collector.db
ENV MEDIA_DIR=/data/media

CMD ["telegram-link-collector", "run-service"]
