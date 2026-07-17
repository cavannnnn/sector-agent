#!/bin/bash
# Render.com build script
set -euo pipefail

echo "=== Building Sector Rotation AI Agent ==="

# Install dependencies
pip install -r requirements.txt

echo "=== Build complete ==="
