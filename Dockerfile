FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml /app/
RUN pip install --upgrade pip && pip install -e .[dev] \
    && (pip install libpff-python || echo "libpff-python unavailable — PST import disabled, mbox/eml still work")

COPY . /app/

RUN mkdir -p /app/data/uploads /app/data/parquet /app/data/reports /app/data/reference

EXPOSE 8000 8501
