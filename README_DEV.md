# Development Setup

This project uses modern Python tooling with **uv** for package management and **ruff** for linting/formatting.

## Quick Start

1. **Install uv:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   export PATH="$HOME/.local/bin:$PATH"
   ```

2. **Run commands directly (no venv activation needed):**
   ```bash
   # Format code
   uv run ruff format src/ scripts/ examples/
   
   # Check linting
   uv run ruff check src/ scripts/ examples/
   
   # Fix auto-fixable issues
   uv run ruff check --fix src/ scripts/ examples/
   
   # Run tests
   uv run pytest
   
   # Type checking
   uv run mypy src/
   ```

## Direct uv Commands

No need to activate virtual environments! uv manages everything:

```bash
# Linting and formatting
uv run ruff check src/ scripts/ examples/          # Check for issues
uv run ruff check --fix src/ scripts/ examples/    # Fix auto-fixable issues  
uv run ruff format src/ scripts/ examples/         # Format code
uv run ruff format --check src/ scripts/ examples/ # Check formatting

# Testing and type checking
uv run pytest                                      # Run tests
uv run pytest --cov=src --cov-report=html         # Run with coverage
uv run mypy src/                                   # Type checking

# Install new dependencies
uv add package-name                                # Add runtime dependency
uv add --dev package-name                         # Add dev dependency
uv remove package-name                            # Remove dependency
```

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
