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

echo "Initializing database..."
if [ -f instance/farm.db ]; then
    echo "Database exists. Skipping deletion to preserve data."
else
    echo "No database found. Creating new..."
fi

python init_db.py

echo "Deployment setup complete!"
echo "Please reload your web app in the PythonAnywhere 'Web' tab."
