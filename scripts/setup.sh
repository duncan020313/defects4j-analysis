#!/bin/bash

# Defects4J Analysis Suite Setup Script
# This script helps set up the environment for the Defects4J analysis tools

set -e

echo "🚀 Setting up Defects4J Analysis Suite..."

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
    echo "❌ Error: Python 3.8+ required, found Python $python_version"
    exit 1
fi

echo "✅ Python $python_version detected"

# Check if uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo "❌ Error: uv not found. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install dependencies using uv
echo "📦 Installing dependencies with uv..."
uv sync

# Check if Defects4J is available
if command -v defects4j >/dev/null 2>&1; then
    echo "✅ Defects4J found: $(defects4j info | head -1)"
else
    echo "⚠️  Defects4J not found in PATH"
    echo "   To use the preprocessing features, install Defects4J:"
    echo "   git clone https://github.com/rjust/defects4j.git"
    echo "   cd defects4j && ./init.sh"
    echo "   export PATH=\$PATH:\$(pwd)/framework/bin"
fi

# Create data directory
mkdir -p data
echo "📁 Created data directory: $(pwd)/data"

# Make scripts executable
chmod +x scripts/*.sh 2>/dev/null || true

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Extract some data:"
echo "   uv run python src/defects4j_extractor.py preprocess --projects Lang --start-id 1 --end-id 5 --out ./data"
echo ""
echo "2. Start the web server:"
echo "   D4J_DATA_DIR=./data uv run uvicorn server.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "3. Open http://localhost:8000 in your browser"
echo ""
