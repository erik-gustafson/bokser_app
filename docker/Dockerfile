FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER root

USER root

WORKDIR /app

COPY docker/requirements.txt /app/requirements.txt

RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY docker/requirements.txt /app/requirements.txt

RUN python -m pip install --no-cache-dir -r /app/requirements.txt

RUN rm -f /app/requirements.txt
RUN rm -f /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY src /app/src

RUN id -u appuser >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data_lake /app/logs /app/downloads /app/test_downloads /app/reporting_archive \
    && chown -R appuser:appuser /app /data_lake /app/logs /app/downloads /app/test_downloads /app/reporting_archive

USER appuser

CMD ["python", "-m", "src.worker.worker"]

