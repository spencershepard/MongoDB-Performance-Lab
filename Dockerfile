FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    wget \
    tar \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Install YCSB
ENV YCSB_VERSION=0.17.0
RUN wget -q https://github.com/brianfrankcooper/YCSB/releases/download/${YCSB_VERSION}/ycsb-${YCSB_VERSION}.tar.gz && \
    tar xfz ycsb-${YCSB_VERSION}.tar.gz && \
    mv ycsb-${YCSB_VERSION} /opt/ycsb && \
    rm ycsb-${YCSB_VERSION}.tar.gz

ENV YCSB_HOME=/opt/ycsb

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
CMD ["mdbpl", "serve", "--host", "0.0.0.0", "--port", "8080"]
