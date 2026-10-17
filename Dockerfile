FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY pyproject.toml README.md ./
COPY hybridforge ./hybridforge
RUN pip install --no-deps .
COPY scripts ./scripts
COPY migrations ./migrations
COPY examples ./examples
RUN useradd --uid 10001 --create-home rag && mkdir /app/data && chown rag:rag /app/data

FROM base AS test
COPY requirements-dev.lock ./
RUN pip install --require-hashes -r requirements-dev.lock
COPY tests ./tests
COPY evals ./evals
USER 10001
CMD ["pytest", "-q"]

FROM base AS runtime
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
CMD ["uvicorn", "hybridforge.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "64"]
