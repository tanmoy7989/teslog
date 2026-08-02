# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Cache mount (not an image layer) so `teslog.sh update`'s rebuilds reuse already-downloaded
# wheels instead of re-fetching all of fastapi/uvicorn/sqlalchemy/etc. from PyPI every time —
# this step reruns on every source change (COPY src invalidates it) regardless of caching.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -e .

EXPOSE 8080

CMD ["teslog"]
