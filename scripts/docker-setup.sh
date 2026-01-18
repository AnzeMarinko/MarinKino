#!/bin/bash
# Setup script for Docker deployment (app + redis only)

set -e

echo "🐳 MarinKino Docker Setup"
echo "========================"

# Create necessary directories
echo "📁 Creating directory structure..."
mkdir -p cache/logs/server

# Copy env file if not exists
if [ ! -f .env ]; then
    echo "📄 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your configuration"
fi

echo "🏗️  Building Docker images..."
docker compose build

echo "🚀 Starting services..."
docker compose up -d

echo "⏳ Waiting for services to be ready..."
sleep 5

echo "✅ Setup complete!"
echo ""
echo "Your services are running:"
echo "  - App: http://localhost:5000"
echo "  - Redis: localhost:6380"
echo ""
echo "View logs with: docker compose logs -f"
echo "Stop services with: docker compose down"
