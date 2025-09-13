#!/usr/bin/env python3
"""
Defects4J extractor: Extract relevant Java method code and leading JavaDoc for each file.

Features:
- Walk a source tree and parse all .java files using Tree-sitter.
- Extract method declarations (incl. constructors) with:
  - fully qualified name (package + class nesting + method)
  - parameter types and names (best-effort via tokens)
  - start/end byte offsets and line numbers
  - method source code snippet
  - leading JavaDoc comment, if present (/** ... */), normalized
- Output a JSONL or JSON file with one entry per method.

Planned additions (subcommands already scaffolded):
- diff mode: find changed methods between buggy and fixed trees (git diff or file-level diff).

Notes:
- Tree-sitter "tree_sitter_languages" provides a ready Java parser.
- This script avoids external Java parsers to keep dependencies light.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple, Set
import subprocess
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor

import orjson
from tree_sitter import Language, Parser
from tree_sitter_languages import get_language


@dataclasses.dataclass
class MethodInfo:
    file_path: str
    package_name: Optional[str]
    class_qualifier: str
    method_name: str
    parameters: List[str]
    return_type: Optional[str]
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    javadoc: Optional[str]
    code: str

    @property
    def fully_qualified_name(self) -> str:
        parts: List[str] = []
        if self.package_name:
            parts.append(self.package_name)
        if self.class_qualifier:
            parts.append(self.class_qualifier)
        parts.append(self.method_name)
        return ".".join(p for p in parts if p)


def load_java_parser() -> Parser:
    language: Language = get_language("java")
    parser = Parser()
    parser.set_language(language)
    return parser


def read_text_bytes(path: Path) -> Tuple[str, bytes]:
    text = path.read_text(encoding="utf-8", errors="replace")
    data = text.encode("utf-8")
    return text, data


def byte_to_line_col(byte_offset: int, text: str) -> Tuple[int, int]:
    # Convert byte offset to 1-based line number and 0-based column from text
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
    col_chars = len(encoded[line_start:line_start+col_bytes].decode("utf-8", errors="ignore"))
    return line, col_chars


def node_text(source_bytes: bytes, node) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def find_package_name(root_node, source_bytes: bytes) -> Optional[str]:
    # Java grammar: package_declaration: 'package' qualified_identifier ';'
    for child in root_node.children:
        if child.type == "package_declaration":
            # find qualified_identifier text
            for ch in child.children:
                if ch.type in ("scoped_identifier", "identifier", "qualified_identifier"):
                    return node_text(source_bytes, ch).strip()
            # fallback to full node text parsing
            text = node_text(source_bytes, child)
            m = re.search(r"package\s+([a-zA-Z0-9_\.]+)\s*;", text)
            if m:
                return m.group(1)
    return None


def is_class_like(node) -> bool:
    return node.type in (
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    )


def is_method_like(node) -> bool:
    # Covers method_declaration and constructor_declaration
    return node.type in ("method_declaration", "constructor_declaration")


def collect_class_stack_names(node, source_bytes: bytes) -> str:
    # Build nested class/interface names like Outer$Inner
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


def find_leading_javadoc(method_node, source_bytes: bytes, text_str: str) -> Optional[str]:
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
    after = snippet[javadoc_match.end():]
    if re.search(r"\S", re.sub(r"(?s)/\*.*?\*/|//.*", "", after)):
        # Non-whitespace content between javadoc and method; consider not directly attached
        return None
    raw = "/**" + javadoc_match.group(1) + "*/"
    return normalize_javadoc(raw)


def normalize_javadoc(raw: str) -> str:
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


def walk_methods(root, source_bytes: bytes, text_str: str, package_name: Optional[str], file_path: str) -> Iterator[MethodInfo]:
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
    for p in root_dir.rglob("*.java"):
        if p.is_file():
            yield p


def extract_from_file(parser: Parser, path: Path) -> List[MethodInfo]:
    text_str, data = read_text_bytes(path)
    tree = parser.parse(data)
    root = tree.root_node
    package_name = find_package_name(root, data)
    methods = list(walk_methods(root, data, text_str, package_name, str(path)))
    return methods


def run_scan(source_root: Path, out_path: Optional[Path], jsonl: bool) -> int:
    parser = load_java_parser()
    results: List[Dict] = []
    count = 0
    files_scanned = 0
    for path in iter_java_files(source_root):
        files_scanned += 1
        try:
            methods = extract_from_file(parser, path)
            for m in methods:
                results.append(dataclasses.asdict(m))
                count += 1
        except Exception as ex:
            # Continue after logging; keep extractor robust over imperfect sources
            print(f"[WARN] Failed to parse {path}: {ex}", file=sys.stderr)

    if out_path is None:
        # print to stdout (jsonl or json)
        if jsonl:
            for rec in results:
                sys.stdout.write(orjson.dumps(rec).decode("utf-8") + "\n")
        else:
            sys.stdout.write(orjson.dumps(results, option=orjson.OPT_INDENT_2).decode("utf-8"))
    else:
        if jsonl:
            with out_path.open("w", encoding="utf-8") as f:
                for rec in results:
                    f.write(orjson.dumps(rec).decode("utf-8") + "\n")
        else:
            out_path.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    return count


def run_diff(buggy_root: Path, fixed_root: Path, out_path: Optional[Path], jsonl: bool) -> int:
    parser = load_java_parser()

    def _normalize_code_for_diff(code: str) -> str:
        # Remove whitespace for lenient structural diff; keep comments to detect comment-only changes in code
        return re.sub(r"\s+", "", code)

    def _signature_tuple(file_rel_path: str, m: MethodInfo) -> Tuple[str, str, str, int]:
        # Use relative path + class qualifier + method name + arity as signature
        return (file_rel_path, m.class_qualifier, m.method_name, len(m.parameters or []))

    def extract_with_rel(root_dir: Path) -> List[Tuple[Tuple[str, str, str, int], MethodInfo]]:
        pairs: List[Tuple[Tuple[str, str, str, int], MethodInfo]] = []
        for path in iter_java_files(root_dir):
            methods = extract_from_file(parser, path)
            rel = os.path.relpath(str(path), str(root_dir))
            rel = rel.replace(os.sep, "/")
            for m in methods:
                sig = _signature_tuple(rel, m)
                pairs.append((sig, m))
        return pairs

    buggy_pairs = extract_with_rel(buggy_root)
    fixed_pairs = extract_with_rel(fixed_root)

    buggy_map: Dict[Tuple[str, str, str, int], MethodInfo] = {k: v for k, v in buggy_pairs}
    fixed_map: Dict[Tuple[str, str, str, int], MethodInfo] = {k: v for k, v in fixed_pairs}

    all_keys: Set[Tuple[str, str, str, int]] = set(buggy_map.keys()) | set(fixed_map.keys())

    results: List[Dict] = []
    count = 0

    for key in sorted(all_keys):
        b = buggy_map.get(key)
        f = fixed_map.get(key)
        status: str
        if b and f:
            code_changed = _normalize_code_for_diff(b.code) != _normalize_code_for_diff(f.code)
            javadoc_b = b.javadoc or ""
            javadoc_f = f.javadoc or ""
            javadoc_changed = javadoc_b != javadoc_f
            if not code_changed and not javadoc_changed:
                continue
            status = "modified"
        elif b and not f:
            status = "removed"
        elif f and not b:
            status = "added"
        else:
            continue

        rec: Dict = {
            "status": status,
            "signature": {
                "file_rel_path": key[0],
                "class_qualifier": key[1],
                "method_name": key[2],
                "arity": key[3],
            },
            "buggy": dataclasses.asdict(b) if b else None,
            "fixed": dataclasses.asdict(f) if f else None,
        }
        results.append(rec)
        count += 1

    if out_path is None:
        if jsonl:
            for rec in results:
                sys.stdout.write(orjson.dumps(rec).decode("utf-8") + "\n")
        else:
            sys.stdout.write(orjson.dumps(results, option=orjson.OPT_INDENT_2).decode("utf-8"))
    else:
        if jsonl:
            with out_path.open("w", encoding="utf-8") as f:
                for rec in results:
                    f.write(orjson.dumps(rec).decode("utf-8") + "\n")
        else:
            out_path.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    return count


def _run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out, err


def _defects4j_bug_ids(project: str) -> List[int]:
    # Query available bug ids via defects4j info -p <proj>
    code, out, err = _run_cmd(["defects4j", "info", "-p", project])
    if code != 0:
        raise RuntimeError(f"defects4j info failed for {project}: {err}")
    ids: List[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Bug.ID") or line.startswith("Bug ID"):
            continue
        # Skip deprecated entries if marked in info output
        if "deprecated" in line.lower():
            continue
        m = re.match(r"^(\d+)\b.*", line)
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def _checkout_bug(project: str, bug_id: int, dest: Path, fixed: bool) -> None:
    version = f"{bug_id}{'f' if fixed else 'b'}"
    code, out, err = _run_cmd(["defects4j", "checkout", "-p", project, "-v", version, "-w", str(dest)])
    if code != 0:
        raise RuntimeError(f"defects4j checkout failed: {project}-{version}: {err}")


def _source_root_for_checkout(workdir: Path, main_only: bool) -> Path:
    # Prefer src/main/java if present and main_only requested, else workdir
    candidate = workdir / "src" / "main" / "java"
    if main_only and candidate.exists():
        return candidate
    return workdir


def preprocess_project(project: str, out_dir: Path, start_id: Optional[int], end_id: Optional[int], main_only: bool, force: bool, stop_on_error: bool = False, jobs: int = 1) -> int:
    ids = _defects4j_bug_ids(project)
    if not ids:
        # Fallback to provided range or a sane default; deprecated bugs will be skipped during checkout
        if start_id is not None or end_id is not None:
            lo_fb = start_id if start_id is not None else 1
            hi_fb = end_id if end_id is not None else lo_fb
            ids = list(range(lo_fb, hi_fb + 1))
        else:
            ids = list(range(1, 201))
    if start_id is not None or end_id is not None:
        lo = start_id if start_id is not None else min(ids) if ids else 1
        hi = end_id if end_id is not None else max(ids) if ids else lo
        ids = [i for i in ids if lo <= i <= hi]
    def _process_one_bug(bug_id: int) -> int:
        out_path = out_dir / f"{project}_{bug_id}.json"
        if out_path.exists() and not force:
            # Skip existing
            return 0
        try:
            with tempfile.TemporaryDirectory(prefix=f"d4j_{project}_{bug_id}_") as tmpd:
                tmp = Path(tmpd)
                buggy = tmp / "buggy"
                fixed = tmp / "fixed"
                _checkout_bug(project, bug_id, buggy, fixed=False)
                _checkout_bug(project, bug_id, fixed, fixed=True)
                buggy_src = _source_root_for_checkout(buggy, main_only)
                fixed_src = _source_root_for_checkout(fixed, main_only)
                # Run diff and write to out_path
                count = run_diff(buggy_src, fixed_src, out_path, jsonl=False)
                print(f"[OK] {project}-{bug_id}: {count} changed method(s)", file=sys.stderr)
                return 1
        except RuntimeError as ex:
            msg = str(ex)
            if "deprecated bug" in msg.lower():
                print(f"[SKIP] {project}-{bug_id}: deprecated bug", file=sys.stderr)
                return 0
            print(f"[WARN] {project}-{bug_id}: {msg}", file=sys.stderr)
            if stop_on_error:
                raise
            return 0
        except Exception as ex:
            print(f"[WARN] {project}-{bug_id}: {ex}", file=sys.stderr)
            if stop_on_error:
                raise
            return 0

    # Normalize jobs
    jobs = int(jobs) if isinstance(jobs, int) else 1
    if jobs < 1:
        jobs = 1

    # Fallback to sequential if requested to stop on first error or single worker
    if stop_on_error or jobs == 1:
        processed = 0
        for bug_id in ids:
            processed += _process_one_bug(bug_id)
        return processed

    processed = 0
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        for result in executor.map(_process_one_bug, ids):
            processed += int(result or 0)
    return processed


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract Java methods and JavaDoc from a source tree using Tree-sitter.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan a single source tree")
    p_scan.add_argument("source", type=str, help="Path to source root directory")
    p_scan.add_argument("--out", type=str, default=None, help="Path to output file (JSON or JSONL)")
    p_scan.add_argument("--jsonl", action="store_true", help="Emit JSON lines instead of a single JSON array")

    p_diff = sub.add_parser("diff", help="Compare buggy and fixed trees and extract relevant methods")
    p_diff.add_argument("buggy", type=str, help="Path to buggy source root")
    p_diff.add_argument("fixed", type=str, help="Path to fixed source root")
    p_diff.add_argument("--out", type=str, default=None, help="Path to output file (JSON or JSONL)")
    p_diff.add_argument("--jsonl", action="store_true", help="Emit JSON lines instead of a single JSON array")

    p_pre = sub.add_parser("preprocess", help="Process Defects4J bugs and build method-level diff data")
    p_pre.add_argument("--projects", type=str, default="Lang,Chart,Time,Math,Mockito", help="Comma-separated list of D4J projects")
    p_pre.add_argument("--out", type=str, default="/root/d4j_data", help="Output directory for per-bug JSON files")
    p_pre.add_argument("--start-id", type=int, default=None, help="Start bug id (inclusive) to process for single project")
    p_pre.add_argument("--end-id", type=int, default=None, help="End bug id (inclusive) to process for single project")
    p_pre.add_argument("--project-only", type=str, default=None, help="If provided, limit to this single project name")
    p_pre.add_argument("--main-only", action="store_true", help="Scan only src/main/java subtrees when present")
    p_pre.add_argument("--force", action="store_true", help="Overwrite existing outputs")
    p_pre.add_argument("--stop-on-error", action="store_true", help="Stop on first checkout/diff error instead of skipping")
    p_pre.add_argument("--jobs", type=int, default=(os.cpu_count() or 4), help="Number of parallel workers for preprocessing (1 disables parallelism)")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(argv)

    out_path = Path(args.out) if getattr(args, "out", None) else None

    if args.cmd == "scan":
        source_root = Path(args.source).resolve()
        if not source_root.exists():
            print(f"Source root not found: {source_root}", file=sys.stderr)
            return 2
        count = run_scan(source_root, out_path, args.jsonl)
        print(f"[OK] Extracted {count} methods from {source_root}", file=sys.stderr)
        return 0
    elif args.cmd == "diff":
        buggy_root = Path(args.buggy).resolve()
        fixed_root = Path(args.fixed).resolve()
        for p in (buggy_root, fixed_root):
            if not p.exists():
                print(f"Path not found: {p}", file=sys.stderr)
                return 2
        count = run_diff(buggy_root, fixed_root, out_path, args.jsonl)
        print(f"[OK] Extracted {count} methods (diff mode) from {buggy_root}", file=sys.stderr)
        return 0
    elif args.cmd == "preprocess":
        projects = [x.strip() for x in (args.project_only or args.projects).split(",") if x.strip()]
        out_dir = Path(args.out).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for proj in projects:
            total += preprocess_project(
                proj,
                out_dir,
                start_id=args.start_id,
                end_id=args.end_id,
                main_only=args.main_only,
                force=args.force,
                stop_on_error=getattr(args, "stop_on_error", False),
                jobs=getattr(args, "jobs", 1),
            )
        print(f"[OK] Preprocessed {total} bug(s) into {out_dir}", file=sys.stderr)
        return 0
    else:
        ap.print_help()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


