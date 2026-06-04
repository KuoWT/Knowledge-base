FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY setup.py /app/setup.py
COPY knowledge_base_api /app/knowledge_base_api

RUN python -m pip install --upgrade pip \
    && python -m pip install /app

EXPOSE 8080

CMD ["python", "-m", "knowledge_base_api.main"]
