FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -p 2222"

RUN mkdir -p /root/.ssh \
    && chmod 700 /root/.ssh

COPY setup.py /app/setup.py
COPY knowledge_base_api /app/knowledge_base_api

RUN python -m pip install --upgrade pip \
    && python -m pip install /app

EXPOSE 8080

CMD ["python", "-m", "knowledge_base_api.main"]
