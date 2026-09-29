FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir . \
    && groupadd --gid 10001 permplaces \
    && useradd --uid 10001 --gid 10001 --create-home \
       --home-dir /home/permplaces --shell /usr/sbin/nologin permplaces \
    && mkdir -p /app/data \
    && chown -R 10001:10001 /app /home/permplaces

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.getenv("HEALTH_PORT", "8080") + "/health/ready", timeout=2).read()' || exit 1

CMD ["python", "-m", "app.main"]
