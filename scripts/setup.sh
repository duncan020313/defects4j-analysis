#!/bin/bash

# Defects4J Analysis Suite Setup Script
# This script helps set up the environment for the Defects4J analysis tools

set -e

echo "🚀 Setting up Defects4J Analysis Suite..."

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.7"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 7) else 1)" 2>/dev/null; then
    echo "❌ Error: Python 3.7+ required, found Python $python_version"
    exit 1
fi

echo "✅ Python $python_version detected"

# Install core dependencies
echo "📦 Installing core dependencies..."
pip3 install -r requirements.txt

# Install server dependencies
echo "📦 Installing server dependencies..."
pip3 install -r server/requirements.txt

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
echo "   python src/defects4j_extractor.py preprocess --projects Lang --start-id 1 --end-id 5 --out ./data"
echo ""
echo "2. Start the web server:"
echo "   cd server && D4J_DATA_DIR=../data uvicorn main:app --host 0.0.0.0 --port 8000"
echo ""
echo "3. Open http://localhost:8000 in your browser"
echo ""
