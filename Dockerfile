FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --default-timeout=1000 --no-cache-dir -e .

# copy source code and other files
COPY credentials ./credentials
COPY src ./src

# Ensure Python can import modules from src
ENV PYTHONPATH=/app/src

# Create necessary directories
RUN mkdir -p /app/cache/logs/server

# Expose port
EXPOSE 5000

# Run the application with waitress
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--trusted-proxy=*", "src.app:app"]
