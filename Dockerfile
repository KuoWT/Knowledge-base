FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root/.ssh \
    && ssh-keyscan -H github.com gitlab.com >> /root/.ssh/known_hosts \
    && chmod 600 /root/.ssh/known_hosts

COPY setup.py /app/setup.py
COPY knowledge_base_api /app/knowledge_base_api

RUN python -m pip install --upgrade pip \
    && python -m pip install /app

EXPOSE 8080

CMD ["python", "-m", "knowledge_base_api.main"]
