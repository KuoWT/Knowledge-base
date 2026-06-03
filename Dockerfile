FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY setup.py /app/setup.py
COPY hermes /app/hermes

RUN python -m pip install --upgrade pip \
    && python -m pip install /app

EXPOSE 8080

CMD ["python", "-m", "hermes.main"]
