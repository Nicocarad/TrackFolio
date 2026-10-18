# TrackFolio application image (multi-arch: builds on x86_64 and aarch64).
FROM docker.io/library/python:3.14-slim AS build
RUN pip install --no-cache-dir uv==0.11.28
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-editable

FROM docker.io/library/python:3.14-slim
RUN useradd --create-home --uid 10001 trackfolio
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER trackfolio
WORKDIR /home/trackfolio
EXPOSE 8000
CMD ["uvicorn", "trackfolio.web.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips=*"]
