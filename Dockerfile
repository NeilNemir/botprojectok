FROM python:3.11-slim

ARG CACHE_BUST=0
LABEL build_timestamp="$CACHE_BUST"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Системные зависимости (если aiogram/ssl/locale)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata && \
    rm -rf /var/lib/apt/lists/*

# Зависимости
COPY requirements.txt /app/requirements.txt
RUN python -m pip install -U pip && pip install -r requirements.txt

# Код
COPY . /app

# Непривилегированный пользователь
RUN useradd -r -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Если в коде БД кладётся в ./data — создадим папку
RUN mkdir -p /app/data /app/logs

CMD ["python", "run.py"]
