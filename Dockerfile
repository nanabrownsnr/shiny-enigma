FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency files
COPY pyproject.toml README.md uv.lock ./

# Build and install dependencies using uv (or pip as fallback)
RUN pip install --no-cache-dir uv 2>/dev/null || true
RUN uv sync --frozen --no-dev 2>/dev/null || \
    pip install --no-cache-dir -e .

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libffi8 \
    && rm -rf /var/lib/apt/lists/*

# Copy the isolated environment without overwriting the base image's Python
# installation and symlink chain.
COPY --from=builder /build/.venv /opt/venv

# Copy application code
COPY ./app /app/app
COPY pyproject.toml README.md uv.lock ./

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
