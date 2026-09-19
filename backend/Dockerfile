# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# No apt-get on purpose: every dependency ships a manylinux wheel, so there is
# nothing to compile, and skipping the toolchain takes well over a minute off
# every cold build. The health check uses Python instead of curl for the same
# reason.

# Dependencies first so the layer is reused whenever only app code changes.
# INSTALL_DEV=true also installs pytest/faker so the demo-data generator can be
# run inside the container (docker compose sets it; hosted deploys do not).
ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; \
    else pip install -r requirements.txt; fi

COPY . .

RUN useradd --create-home --uid 1000 edumatch \
    && mkdir -p /app/storage/uploads \
    && chown -R edumatch:edumatch /app
USER edumatch

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8000')+'/health').read()" || exit 1

# Migrations run at boot so `docker compose up` is genuinely one command.
# $PORT is honoured because most platforms (Render, Railway, Cloud Run, Heroku)
# assign the port at runtime rather than letting the image choose it.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips '*'"]
