# ═══════════════════════════════════════════════════════════════
# MEMEX — Local-First Passive Second Brain
# Multi-stage Dockerfile for reproducible builds
# ═══════════════════════════════════════════════════════════════

# Stage 1: Builder — install dependencies
FROM python:3.13-slim AS builder

WORKDIR /build

# Install system deps for building native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY memex/ memex/

RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Runtime — minimal image
FROM python:3.13-slim

LABEL org.opencontainers.image.title="MEMEX"
LABEL org.opencontainers.image.description="Local-First Passive Second Brain"
LABEL org.opencontainers.image.version="2.0.0"

# Runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create memex user
RUN useradd -m -s /bin/bash memex

# Create data directory
RUN mkdir -p /home/memex/.memex/data /home/memex/.memex/logs \
    && chown -R memex:memex /home/memex/.memex

WORKDIR /home/memex

# Copy application code
COPY --chown=memex:memex . /home/memex/app/
WORKDIR /home/memex/app

# Environment
ENV MEMEX_DATA_DIR=/home/memex/.memex
ENV MEMEX_LOG_LEVEL=INFO
ENV OLLAMA_HOST=127.0.0.1:11434

USER memex

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:7700/api/health || exit 1

# Start Ollama in background, then memex daemon
COPY <<'EOF' /home/memex/entrypoint.sh
#!/bin/bash
set -e

# Start Ollama server
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama ready."
        break
    fi
    sleep 1
done

# Pull required models if not present
ollama pull nomic-embed-text || true
ollama pull llama3:8b || true

# Start MEMEX daemon
exec memex start
EOF

RUN sudo chown memex:memex /home/memex/entrypoint.sh 2>/dev/null || true
USER root
RUN chmod +x /home/memex/entrypoint.sh
USER memex

EXPOSE 7700

ENTRYPOINT ["/home/memex/entrypoint.sh"]
