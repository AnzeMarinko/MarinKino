FROM python:3.12-slim AS base
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv venv /opt/certbot \
    && uv pip install --python /opt/certbot/bin/python --upgrade certbot \
    && uv pip check --python /opt/certbot/bin/python

FROM base AS runtime
COPY --from=builder /opt/certbot /opt/certbot
ENV PATH="/opt/certbot/bin:$PATH"
LABEL io.marinkino.security.managed="true"
ENTRYPOINT ["certbot"]
CMD ["--version"]
