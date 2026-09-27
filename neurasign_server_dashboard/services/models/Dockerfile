FROM python:3.12-slim
WORKDIR /app
COPY services/models/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY services/models /app/services/models
RUN useradd --system --uid 10002 --create-home neurasign
ENV MODEL_ENGINE_HOST=0.0.0.0
ENV MODEL_BUNDLE_DIR=/app/var/model-engine
ENV PYTHONUNBUFFERED=1
ENV OPENBLAS_NUM_THREADS=1
ENV OMP_NUM_THREADS=1
USER neurasign
EXPOSE 8010
CMD ["python", "services/models/server.py"]
