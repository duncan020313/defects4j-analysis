"""
Tree-sitter parser and AST processing functionality.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

# Suppress FutureWarning from tree-sitter library
warnings.filterwarnings("ignore", category=FutureWarning, module="tree_sitter")

from tree_sitter import Language, Parser
from tree_sitter_languages import get_language

from .models import MethodInfo


def load_java_parser() -> Parser:
    """Load and configure a Tree-sitter Java parser."""
    language: Language = get_language("java")
    parser = Parser()
    parser.set_language(language)
    return parser


def read_text_bytes(path: Path) -> Tuple[str, bytes]:
    """Read a file as both text and bytes for Tree-sitter parsing."""
    text = path.read_text(encoding="utf-8", errors="replace")
    data = text.encode("utf-8")
    return text, data


def byte_to_line_col(byte_offset: int, text: str) -> Tuple[int, int]:
    """Convert byte offset to 1-based line number and 0-based column from text."""
    # We operate on unicode text. For safety we re-encode to bytes and count newlines.
    encoded = text.encode("utf-8")
    if byte_offset > len(encoded):
        byte_offset = len(encoded)
    prefix = encoded[:byte_offset]
    line = prefix.count(b"\n") + 1
    last_nl = prefix.rfind(b"\n")
    if last_nl == -1:
        col_bytes = len(prefix)
    else:
        col_bytes = len(prefix) - last_nl - 1
    # Convert column in bytes to characters by decoding tail slice
    line_start = 0 if last_nl == -1 else last_nl + 1
    col_chars = len(
        encoded[line_start : line_start + col_bytes].decode("utf-8", errors="ignore")
    )
    return line, col_chars


def node_text(source_bytes: bytes, node) -> str:
    """Extract text content from a Tree-sitter node."""
    return source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )


def find_package_name(root_node, source_bytes: bytes) -> Optional[str]:
    """Extract package name from Java AST root node."""
    # Java grammar: package_declaration: 'package' qualified_identifier ';'
    for child in root_node.children:
        if child.type == "package_declaration":
            # find qualified_identifier text
            for ch in child.children:
                if ch.type in (
                    "scoped_identifier",
                    "identifier",
                    "qualified_identifier",
                ):
                    return node_text(source_bytes, ch).strip()
            # fallback to full node text parsing
            text = node_text(source_bytes, child)
            m = re.search(r"package\s+([a-zA-Z0-9_\.]+)\s*;", text)
            if m:
                return m.group(1)
    return None


def is_class_like(node) -> bool:
    """Check if a Tree-sitter node represents a class-like declaration."""
    return node.type in (
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    )


def is_method_like(node) -> bool:
    """Check if a Tree-sitter node represents a method-like declaration."""
    # Covers method_declaration and constructor_declaration
    return node.type in ("method_declaration", "constructor_declaration")


def collect_class_stack_names(node, source_bytes: bytes) -> str:
    """Build nested class/interface names like Outer$Inner."""
    names: List[str] = []
    stack: List = []
    cur = node
    while cur is not None:
        stack.append(cur)
        cur = cur.parent
    for ancestor in reversed(stack):
        if is_class_like(ancestor):
            # find identifier child
            ident = None
            for ch in ancestor.children:
                if ch.type == "identifier":
                    ident = node_text(source_bytes, ch).strip()
                    break
            if ident:
                names.append(ident)
    return "$".join(names)


def extract_parameters(param_node, source_bytes: bytes) -> List[str]:
    """Extract parameter information from a formal_parameters node."""
    # For parameter list, collect simplified type and name token text
    # Grammar: formal_parameters -> '(' (receiver_parameter | formal_parameter (',' formal_parameter)*)? ')'
    params: List[str] = []
    for ch in param_node.children:
        if ch.type in ("formal_parameter", "receiver_parameter", "spread_parameter"):
            text = node_text(source_bytes, ch)
            # collapse whitespace
            text = re.sub(r"\s+", " ", text).strip()
            params.append(text)
    return params


def find_leading_javadoc(
    method_node, source_bytes: bytes, text_str: str
) -> Optional[str]:
    """Find leading JavaDoc comment for a method node."""
    # Strategy: look at preceding siblings and trivia before method start; Tree-sitter Java exposes comments as 'comment' tokens
    # We gather the closest block comment that starts with '/**'
    start_byte = method_node.start_byte
    # Scan backwards from start_byte within some window (e.g., up to class start) to find a javadoc block immediately preceding
    window_start = max(0, start_byte - 20_000)
    snippet = source_bytes[window_start:start_byte].decode("utf-8", errors="replace")
    # Find the last /** ... */ before start
    javadoc_match = None
    for m in re.finditer(r"/\*\*([\s\S]*?)\*/", snippet):
        javadoc_match = m
    if javadoc_match is None:
        return None
    # Ensure there is only whitespace/comments between end of javadoc and method start
    after = snippet[javadoc_match.end() :]
    if re.search(r"\S", re.sub(r"(?s)/\*.*?\*/|//.*", "", after)):
        # Non-whitespace content between javadoc and method; consider not directly attached
        return None
    raw = "/**" + javadoc_match.group(1) + "*/"
    return normalize_javadoc(raw)


def normalize_javadoc(raw: str) -> str:
    """Normalize JavaDoc content by removing comment markers and leading asterisks."""
    # Remove leading /** and trailing */ and normalize leading * prefixes
    body = raw.strip()
    if body.startswith("/**"):
        body = body[3:]
    if body.endswith("*/"):
        body = body[:-2]
    lines = body.splitlines()
    cleaned: List[str] = []
    for line in lines:
        line = line.rstrip()
        line = re.sub(r"^\s*\* ?", "", line)
        cleaned.append(line)
    # Trim surrounding blank lines
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    return "\n".join(cleaned)


def walk_methods(
    root,
    source_bytes: bytes,
    text_str: str,
    package_name: Optional[str],
    file_path: str,
) -> Iterator[MethodInfo]:
    """Walk AST and extract all method information."""
    # DFS traversal collecting methods
    stack: List = [root]
    while stack:
        node = stack.pop()
        if is_method_like(node):
            class_qualifier = collect_class_stack_names(node, source_bytes)
            method_name = "<init>" if node.type == "constructor_declaration" else None
            return_type: Optional[str] = None
            param_list: List[str] = []

            for ch in node.children:
                if node.type == "method_declaration":
                    if ch.type == "identifier":
                        method_name = node_text(source_bytes, ch).strip()
                    elif ch.type == "formal_parameters":
                        param_list = extract_parameters(ch, source_bytes)
                    elif ch.type == "type":
                        # attempt to capture return type
                        return_type = node_text(source_bytes, ch).strip()
                elif node.type == "constructor_declaration":
                    if ch.type == "formal_parameters":
                        param_list = extract_parameters(ch, source_bytes)

            if method_name is None:
                # Fallback: derive from text
                text_node = node_text(source_bytes, node)
                m = re.search(r"([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(", text_node)
                method_name = m.group(1) if m else "<unknown>"

            start_line, _ = byte_to_line_col(node.start_byte, text_str)
            end_line, _ = byte_to_line_col(node.end_byte, text_str)
            code = node_text(source_bytes, node)
            javadoc = find_leading_javadoc(node, source_bytes, text_str)

            yield MethodInfo(
                file_path=file_path,
                package_name=package_name,
                class_qualifier=class_qualifier,
                method_name=method_name,
                parameters=param_list,
                return_type=return_type,
                start_line=start_line,
                end_line=end_line,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                javadoc=javadoc,
                code=code,
            )
        # push children
        for ch in reversed(node.children or []):
            stack.append(ch)


def iter_java_files(root_dir: Path) -> Iterator[Path]:
    """Iterate over all .java files in a directory tree."""
    for p in root_dir.rglob("*.java"):
        if p.is_file():
            yield p


def extract_from_file(parser: Parser, path: Path) -> List[MethodInfo]:
    """Extract all method information from a single Java file."""
    text_str, data = read_text_bytes(path)
    tree = parser.parse(data)
    root = tree.root_node
    package_name = find_package_name(root, data)
    methods = list(walk_methods(root, data, text_str, package_name, str(path)))
    return methods
