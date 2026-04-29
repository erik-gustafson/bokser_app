FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY docker/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY src /app/src

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data_lake /app/logs /app/downloads /app/test_downloads /app/reporting_archive \
    && chown -R appuser:appuser /app /data_lake /app/logs /app/downloads /app/test_downloads /app/reporting_archive

USER appuser

CMD ["python", "-m", "src.worker.worker"]