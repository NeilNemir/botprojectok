FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install -U pip && pip install -r requirements.txt

COPY . /app

RUN useradd -r -u 10001 appuser && mkdir -p /app/data /app/logs && chown -R appuser:appuser /app
USER appuser

CMD ["python", "run.py"]