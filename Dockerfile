FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY web ./web
COPY scripts ./scripts
COPY examples ./examples
RUN pip install --no-cache-dir ".[full]"
ENV PYTHONUNBUFFERED=1
ENV HARNESS_DEMO_REPO=/app/examples/demo
CMD ["harness"]
