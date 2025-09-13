#!/bin/bash

# Extract a small sample dataset for testing
# This script extracts the first few bugs from Lang and Chart projects

set -e

DATA_DIR="${1:-./data}"
echo "🔍 Extracting sample Defects4J data to: $DATA_DIR"

# Check if defects4j is available
if ! command -v defects4j >/dev/null 2>&1; then
    echo "❌ Error: defects4j not found in PATH"
    echo "Please install Defects4J first. See README.md for instructions."
    exit 1
fi

# Extract first 3 bugs from Lang and Chart (quick sample)
echo "📊 Extracting Lang bugs 1-3..."
uv run python src/defects4j_extractor.py preprocess \
    --project-only Lang \
    --start-id 1 \
    --end-id 3 \
    --main-only \
    --out "$DATA_DIR"

echo "📊 Extracting Chart bugs 1-2..."
uv run python src/defects4j_extractor.py preprocess \
    --project-only Chart \
    --start-id 1 \
    --end-id 2 \
    --main-only \
    --out "$DATA_DIR"

echo ""
echo "✅ Sample extraction complete!"
echo "📁 Data location: $DATA_DIR"
echo ""
echo "Files created:"
ls -la "$DATA_DIR"/*.json 2>/dev/null || echo "No JSON files found"
echo ""
echo "🌐 Start the web server to browse:"
echo "D4J_DATA_DIR=$DATA_DIR uv run uvicorn server.main:app --port 8000"
