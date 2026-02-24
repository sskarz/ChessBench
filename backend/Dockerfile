FROM python:3.11-slim

# Install Stockfish — try AVX2 build first, fall back to SSE41 for hosts
# without AVX2 support (e.g. Render free tier).
RUN apt-get update && \
    apt-get install -y --no-install-recommends wget && \
    ( wget -q https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-avx2.tar -O /tmp/stockfish.tar && \
      tar xf /tmp/stockfish.tar -C /tmp && \
      cp /tmp/stockfish/stockfish-ubuntu-x86-64-avx2 /usr/local/bin/stockfish ) || \
    ( wget -q https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64-sse41-popcnt.tar -O /tmp/stockfish.tar && \
      tar xf /tmp/stockfish.tar -C /tmp && \
      cp /tmp/stockfish/stockfish-ubuntu-x86-64-sse41-popcnt /usr/local/bin/stockfish ) && \
    chmod +x /usr/local/bin/stockfish && \
    rm -rf /tmp/stockfish* && \
    apt-get purge -y wget && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/ src/

# Create data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
