FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

COPY docker/requirements.txt /app/requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt \
    && python -m pip check \
    && python -m pip uninstall -y pip \
    && rm -f /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY src /app/src

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data_lake /app/downloads \
       /app/test_downloads /app/reporting_archive \
    && chown -R appuser:appuser /app /data_lake

USER appuser

CMD ["python", "-m", "src.worker.worker"]