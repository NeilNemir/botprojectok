FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps
# If requirements.txt exists, use it; otherwise install known deps
COPY requirements.txt /tmp/requirements.txt
RUN if [ -s /tmp/requirements.txt ]; then \
      pip install --no-cache-dir -r /tmp/requirements.txt; \
    else \
      pip install --no-cache-dir aiogram python-dotenv gspread google-auth; \
    fi

# Copy app
COPY . /app

# Default command
CMD ["python", "-u", "run.py"]
