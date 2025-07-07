#!/bin/bash
# Setup and launch the PHP upload server

set -e

# Move to script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Install PHP if missing
if ! command -v php >/dev/null 2>&1; then
    echo "PHP not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y php-cli
fi

# Create uploads directory if needed
mkdir -p uploads

# Start PHP built-in server
echo "Starting PHP server on http://localhost:8000"
php -S 0.0.0.0:8000 &

