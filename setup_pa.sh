#!/bin/bash
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Checking environment variables..."
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.template .env
    KEY=$(python generate_key.py)
    # Replace the empty key in .env with the generated one
    sed -i "s/SECRET_KEY=/SECRET_KEY=$KEY/" .env
    echo "Generated new SECRET_KEY in .env"
else
    echo ".env file already exists."
fi

# Detect Database Mode (Postgres vs SQLite)
# Check for 'postgres' anywhere in the DATABASE_URL line
if grep -q "DATABASE_URL=.*postgres" .env; then
    echo "PostgreSQL detected in .env"
    DB_MODE="postgres"
else
    echo "SQLite detected (default)"
    DB_MODE="sqlite"
fi

echo "Checking database..."
if [ "$DB_MODE" = "sqlite" ] && [ -f instance/farm.db ]; then
    echo "Backing up existing SQLite database..."
    cp instance/farm.db instance/farm.db.bak
    echo "Backup created at instance/farm.db.bak"
fi

echo "Checking migration status..."
python fix_migration_conflict.py

echo "Running migrations..."
flask db upgrade

echo "Initializing/Updating database..."
python init_db.py

echo "Deployment setup complete!"
echo "Please reload your web app in the PythonAnywhere 'Web' tab."
