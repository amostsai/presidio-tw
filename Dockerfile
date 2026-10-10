FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PII_CONFIG=/data/config/rules.yaml \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --user-group --create-home app \
    && install -d -o app -g app /data/config /models

COPY requirements.txt docker/constraints.txt /app/dependencies/
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 \
    && python -m pip install --no-cache-dir -r dependencies/requirements.txt -c dependencies/constraints.txt \
    && python -m pip check

COPY --chown=app:app web.py restoration.py docker_start.py app.py ./
COPY --chown=app:app pii_service/ ./pii_service/
COPY --chown=app:app file_adapters/ ./file_adapters/
COPY --chown=app:app static/ ./static/
COPY --chown=app:app templates/ ./templates/
COPY --chown=app:app config/rules.yaml config/rule_templates.yaml ./config/

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/config',timeout=3).read()"
CMD ["python", "docker_start.py"]
