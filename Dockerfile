# Kachra Report Card: API + front end in one container.
#
#   docker build -t kachra .
#   docker run -p 8000:8000 -e GEMINI_API_KEY=... kachra
#
# BASE and INSTALL_DEPS exist so the image can be built offline from a base that
# already has the Python packages (INSTALL_DEPS=0). Normal builds leave both alone.
ARG BASE=python:3.12-slim
FROM ${BASE}

ARG INSTALL_DEPS=1
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN if [ "$INSTALL_DEPS" = "1" ]; then pip install --no-cache-dir -r requirements.txt; fi

COPY app ./app
COPY scripts ./scripts
COPY static ./static
COPY evals ./evals

# Run as a non-root user; reports, photos and audio live on the /data volume.
RUN mkdir -p /data /tmp && chmod 1777 /tmp && chown -R 10001:10001 /data
USER 10001
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'), timeout=4)"]

CMD ["sh", "-c", "python -m scripts.seed_demo_if_empty && exec python -m uvicorn app.server:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
