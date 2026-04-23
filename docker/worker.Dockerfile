FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY docker/requirements.worker.txt /tmp/requirements.worker.txt
RUN pip install --no-cache-dir -r /tmp/requirements.worker.txt \
    && rm -f /tmp/requirements.worker.txt

COPY src /app/src

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data_lake \
    && chown -R appuser:appuser /app /data_lake

USER appuser

CMD ["python", "-m", "src.worker.worker"]

