FROM python:3.12-slim AS base
ARG SECURITY_REFRESH=initial
WORKDIR /app
RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ARG UPDATE_DEPENDENCIES=0
# Optional preparation/ML tools never enter the public server image.
RUN if [ "$UPDATE_DEPENDENCIES" = 1 ]; then uv lock --upgrade; fi \
    && uv sync --frozen --no-dev --no-editable

FROM base AS runtime
LABEL io.marinkino.security.managed="true"
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid "$APP_GID" marinkino \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --no-create-home --shell /usr/sbin/nologin marinkino \
    && mkdir -p /app/data /app/cache /run/marinkino \
    && chown "$APP_UID:$APP_GID" /app/data /app/cache /run/marinkino \
    && chmod 755 /run/marinkino
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/uv.lock /app/runtime.lock
ENV PATH=/app/.venv/bin:/usr/local/bin:/usr/bin:/bin XDG_CACHE_HOME=/tmp/cache
USER ${APP_UID}:${APP_GID}
HEALTHCHECK --interval=20s --timeout=5s --start-period=60s --retries=5 CMD ["python", "-m", "healthcheck"]
CMD ["python", "-m", "serve"]
