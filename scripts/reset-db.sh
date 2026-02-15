#!/bin/bash
set -e

echo "⚠️  WARNING: This will delete all data in the database!"
read -p "Are you sure you want to continue? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo "🗑️  Resetting database..."

# Stop containers
docker-compose down

# Remove volumes
docker volume rm miaobu_postgres_data 2>/dev/null || true

# Start database
docker-compose up -d postgres redis

echo "⏳ Waiting for database to be ready..."
sleep 5

# Run migrations
echo "📊 Running migrations..."
docker-compose run --rm backend alembic upgrade head

# Start all services
docker-compose up -d

echo "✅ Database reset complete!"
