FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Install MongoDB Shell (mongosh) - download standalone binary
ENV MONGOSH_VERSION=2.1.1
RUN wget -q https://downloads.mongodb.com/compass/mongosh-${MONGOSH_VERSION}-linux-x64.tgz && \
    tar -xzf mongosh-${MONGOSH_VERSION}-linux-x64.tgz && \
    mv mongosh-${MONGOSH_VERSION}-linux-x64/bin/mongosh /usr/local/bin/ && \
    mv mongosh-${MONGOSH_VERSION}-linux-x64/bin/mongosh_crypt_v1.so /usr/local/lib/ || true && \
    chmod +x /usr/local/bin/mongosh && \
    rm -rf mongosh-${MONGOSH_VERSION}-linux-x64* && \
    mongosh --version

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the CLI tool
RUN pip install --no-cache-dir -e .

# Create data directory for SQLite
RUN mkdir -p /data

# Expose API port
EXPOSE 8080

# Default command (can be overridden in docker-compose)
CMD ["mdbpl", "serve", "--host", "0.0.0.0", "--port", "8888"]
