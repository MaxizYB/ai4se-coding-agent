FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY web ./web
COPY scripts ./scripts
RUN pip install --no-cache-dir ".[full]"
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["harness"]
