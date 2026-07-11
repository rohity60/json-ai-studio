FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
       && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
ENV PYTHONPATH="/app/src"

# Logging (ADR-0017): write rotating log files here. docker-compose bind-mounts
# ./logs/api over this dir so logs persist on the host. The app also mkdirs it
# at runtime, so this works even without the mount.
ENV LOG_DIR="/app/logs"
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "json_ai_studio.main:app", "--host", "0.0.0.0", "--port", "8000"]
