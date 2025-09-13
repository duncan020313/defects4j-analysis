# Development Setup

This project uses modern Python tooling with **uv** for package management and **ruff** for linting/formatting.

## Quick Start

1. **Install dependencies:**
   ```bash
   # Make sure uv is installed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   export PATH="$HOME/.local/bin:$PATH"
   
   # Install project dependencies
   uv venv
   uv pip install tree-sitter tree-sitter-languages orjson fastapi uvicorn ruff mypy pytest pytest-cov pytest-xdist
   ```

2. **Activate virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Run development commands:**
   ```bash
   # Format code
   python scripts/dev.py format
   
   # Lint code
   python scripts/dev.py lint
   
   # Fix linting issues
   python scripts/dev.py fix
   
   # Run tests
   python scripts/dev.py test
   
   # Run all checks
   python scripts/dev.py check-all
   ```

## Development Commands

The `scripts/dev.py` script provides common development tasks:

- `format` - Format code with ruff
- `format-check` - Check if code is properly formatted  
- `lint` - Run ruff linter
- `fix` - Fix linting issues automatically
- `typecheck` - Run mypy type checking
- `test` - Run pytest tests
- `test-cov` - Run tests with coverage report
- `check-all` - Run all checks (lint, format-check, typecheck, test)

## Project Structure

```
defects4j-analysis/
├── src/                    # Source code
│   └── defects4j_extractor/
├── server/                 # FastAPI web server
├── scripts/               # Development and utility scripts
├── examples/              # Example usage
├── tests/                 # Test files (to be created)
├── pyproject.toml         # Project configuration
├── .gitignore            # Git ignore rules
└── .venv/                # Virtual environment (created by uv)
```

## Tools Configuration

All tools are configured in `pyproject.toml`:

- **ruff**: Linting and formatting with sensible defaults
- **mypy**: Type checking configuration
- **pytest**: Test configuration with coverage
- **uv**: Dependency management

## Dependencies

### Core Dependencies
- `tree-sitter>=0.20.0` - For parsing source code
- `tree-sitter-languages>=1.8.0` - Language grammars
- `orjson>=3.8.0` - Fast JSON handling

### Server Dependencies  
- `fastapi>=0.100.0` - Web framework
- `uvicorn[standard]>=0.20.0` - ASGI server

### Development Dependencies
- `ruff>=0.1.0` - Linting and formatting
- `mypy>=1.0.0` - Type checking
- `pytest>=7.0.0` - Testing framework
- `pytest-cov>=4.0.0` - Coverage reporting
- `pytest-xdist>=3.0.0` - Parallel test execution
