# syntax=docker/dockerfile:1

# ---- build: turn the project and its dependencies into wheels ----
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# ---- runtime: only the installed package, no build tools, non-root user ----
FROM python:3.12-slim
ARG UID=1000
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOB_COLLECTOR_CONFIG=/app/config/config.yaml \
    GOOGLE_CREDENTIALS=/app/credentials/service-account.json
RUN useradd --uid "${UID}" --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY config ./config
USER app
ENTRYPOINT ["job-collector"]
