#!/bin/bash
set -e

echo "🚀 Setting up Miaobu development environment..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file. Please update it with your credentials."
fi

# Start services
echo "📦 Starting Docker containers..."
docker-compose up -d postgres redis

echo "⏳ Waiting for database to be ready..."
sleep 5

# Build backend
echo "🔨 Building backend..."
docker-compose build backend

# Run migrations
echo "📊 Running database migrations..."
docker-compose run --rm backend alembic upgrade head

# Start all services
echo "🎉 Starting all services..."
docker-compose up -d

echo ""
echo "✅ Setup complete!"
echo ""
echo "Services:"
echo "  - Frontend: http://localhost:5173"
echo "  - Backend API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
echo "View logs with: docker-compose logs -f"
echo "Stop services with: docker-compose down"
