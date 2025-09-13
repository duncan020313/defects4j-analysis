#!/usr/bin/env python3
"""
Defects4J extractor: Extract relevant Java method code and leading JavaDoc for each file.

This is the main entry point that imports from the refactored submodules.
For detailed functionality, see the individual modules:
- defects4j_extractor.models: Data models (MethodInfo, BugMetadata, etc.)
- defects4j_extractor.parser: Tree-sitter parsing and AST processing
- defects4j_extractor.extractor: Core extraction functionality (scan, diff)
- defects4j_extractor.defects4j: Defects4J integration and preprocessing
- defects4j_extractor.cli: Command-line interface

Features:
- Walk a source tree and parse all .java files using Tree-sitter.
- Extract method declarations (incl. constructors) with:
  - fully qualified name (package + class nesting + method)
  - parameter types and names (best-effort via tokens)
  - start/end byte offsets and line numbers
  - method source code snippet
  - leading JavaDoc comment, if present (/** ... */), normalized
- Output a JSONL or JSON file with one entry per method.
- diff mode: find changed methods between buggy and fixed trees.
- preprocess mode: process Defects4J bugs and build method-level diff data.

Notes:
- Tree-sitter "tree_sitter_languages" provides a ready Java parser.
- This script avoids external Java parsers to keep dependencies light.
"""

from __future__ import annotations

from defects4j_extractor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
