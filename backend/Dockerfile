FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1

# Install build deps for psycopg/asyncpg wheels are fine; nothing else needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install -e .

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh ./

EXPOSE 8000

CMD ["./entrypoint.sh"]
