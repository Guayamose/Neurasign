FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY services/api /app/services/api
COPY data/fixtures /app/data/fixtures
RUN useradd --system --uid 10001 --create-home neurasign && mkdir -p /app/var && chown neurasign:neurasign /app/var
ENV PYTHONPATH=/app/services/api
ENV PYTHONUNBUFFERED=1
USER neurasign
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn neurasign.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --no-server-header"]
