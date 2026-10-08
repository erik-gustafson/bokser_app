FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY docker/terminal49-requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt \
    && python -m pip check && rm /app/requirements.txt
COPY src/integrations/terminal49_client /app/src/integrations/terminal49_client
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data_lake && chown -R appuser:appuser /app /data_lake
USER appuser
CMD ["python", "-m", "src.integrations.terminal49_client.worker"]
