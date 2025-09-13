"""
Core extraction functionality for scanning and diffing Java source trees.
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import orjson

from .models import MethodInfo
from .parser import extract_from_file, iter_java_files, load_java_parser


def run_scan(source_root: Path, out_path: Optional[Path], jsonl: bool) -> int:
    """Scan a single source tree and extract all methods."""
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
            sys.stdout.write(
                orjson.dumps(results, option=orjson.OPT_INDENT_2).decode("utf-8")
            )
    else:
        if jsonl:
            with out_path.open("w", encoding="utf-8") as f:
                for rec in results:
                    f.write(orjson.dumps(rec).decode("utf-8") + "\n")
        else:
            out_path.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    return count


def run_diff(
    buggy_root: Path, fixed_root: Path, out_path: Optional[Path], jsonl: bool
) -> int:
    """Compare buggy and fixed trees and extract relevant methods."""
    parser = load_java_parser()

    def _normalize_code_for_diff(code: str) -> str:
        # Remove whitespace for lenient structural diff; keep comments to detect comment-only changes in code
        return re.sub(r"\s+", "", code)

    def _signature_tuple(
        file_rel_path: str, m: MethodInfo
    ) -> Tuple[str, str, str, int]:
        # Use relative path + class qualifier + method name + arity as signature
        return (
            file_rel_path,
            m.class_qualifier,
            m.method_name,
            len(m.parameters or []),
        )

    def extract_with_rel(
        root_dir: Path,
    ) -> List[Tuple[Tuple[str, str, str, int], MethodInfo]]:
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

    buggy_map: Dict[Tuple[str, str, str, int], MethodInfo] = {
        k: v for k, v in buggy_pairs
    }
    fixed_map: Dict[Tuple[str, str, str, int], MethodInfo] = {
        k: v for k, v in fixed_pairs
    }

    all_keys: Set[Tuple[str, str, str, int]] = set(buggy_map.keys()) | set(
        fixed_map.keys()
    )

    results: List[Dict] = []
    count = 0

    for key in sorted(all_keys):
        b = buggy_map.get(key)
        f = fixed_map.get(key)
        status: str
        if b and f:
            code_changed = _normalize_code_for_diff(b.code) != _normalize_code_for_diff(
                f.code
            )
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
            sys.stdout.write(
                orjson.dumps(results, option=orjson.OPT_INDENT_2).decode("utf-8")
            )
    else:
        if jsonl:
            with out_path.open("w", encoding="utf-8") as f:
                for rec in results:
                    f.write(orjson.dumps(rec).decode("utf-8") + "\n")
        else:
            out_path.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    return count
