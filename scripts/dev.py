#!/usr/bin/env python3
"""
Development utility script for defects4j-analysis project.
Provides common development tasks like linting, formatting, and testing.
"""

import subprocess
import sys
from pathlib import Path
from typing import List

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent


def run_command(cmd: List[str], cwd: Path = PROJECT_ROOT) -> int:
    """Run a command and return its exit code."""
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd).returncode


def lint() -> int:
    """Run ruff linter on the project."""
    return run_command(["uv", "run", "ruff", "check", "src/", "scripts/", "examples/"])


def format_code() -> int:
    """Format code using ruff."""
    return run_command(["uv", "run", "ruff", "format", "src/", "scripts/", "examples/"])


def format_check() -> int:
    """Check if code is properly formatted."""
    return run_command(
        ["uv", "run", "ruff", "format", "--check", "src/", "scripts/", "examples/"]
    )


def typecheck() -> int:
    """Run mypy type checking."""
    return run_command(["uv", "run", "mypy", "src/"])


def test() -> int:
    """Run pytest tests."""
    return run_command(["uv", "run", "pytest", "-v"])


def test_coverage() -> int:
    """Run tests with coverage report."""
    return run_command(
        ["uv", "run", "pytest", "--cov=src", "--cov-report=html", "--cov-report=term"]
    )


def fix() -> int:
    """Fix linting issues automatically."""
    return run_command(
        ["uv", "run", "ruff", "check", "--fix", "src/", "scripts/", "examples/"]
    )


def check_all() -> int:
    """Run all checks (lint, format-check, typecheck, test)."""
    checks = [
        ("Linting", lint),
        ("Format check", format_check),
        ("Type checking", typecheck),
        ("Tests", test),
    ]

    failed = []
    for name, check_func in checks:
        print(f"\n=== {name} ===")
        if check_func() != 0:
            failed.append(name)

    if failed:
        print(f"\n❌ Failed checks: {', '.join(failed)}")
        return 1
    print("\n✅ All checks passed!")
    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/dev.py <command>")
        print("Commands:")
        print("  lint        - Run ruff linter")
        print("  format      - Format code with ruff")
        print("  format-check - Check if code is formatted")
        print("  typecheck   - Run mypy type checking")
        print("  test        - Run tests")
        print("  test-cov    - Run tests with coverage")
        print("  fix         - Fix linting issues")
        print("  check-all   - Run all checks")
        return 1

    command = sys.argv[1]

    commands = {
        "lint": lint,
        "format": format_code,
        "format-check": format_check,
        "typecheck": typecheck,
        "test": test,
        "test-cov": test_coverage,
        "fix": fix,
        "check-all": check_all,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        return 1

    return commands[command]()


if __name__ == "__main__":
    sys.exit(main())
