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

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "json_ai_studio.main:app", "--host", "0.0.0.0", "--port", "8000"]
