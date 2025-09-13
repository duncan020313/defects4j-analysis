"""
Command-line interface for the Defects4J extractor.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .defects4j import preprocess_project
from .extractor import run_diff, run_scan


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    p = argparse.ArgumentParser(
        description="Extract Java methods and JavaDoc from a source tree using Tree-sitter."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan a single source tree")
    p_scan.add_argument("source", type=str, help="Path to source root directory")
    p_scan.add_argument(
        "--out", type=str, default=None, help="Path to output file (JSON or JSONL)"
    )
    p_scan.add_argument(
        "--jsonl",
        action="store_true",
        help="Emit JSON lines instead of a single JSON array",
    )

    p_diff = sub.add_parser(
        "diff", help="Compare buggy and fixed trees and extract relevant methods"
    )
    p_diff.add_argument("buggy", type=str, help="Path to buggy source root")
    p_diff.add_argument("fixed", type=str, help="Path to fixed source root")
    p_diff.add_argument(
        "--out", type=str, default=None, help="Path to output file (JSON or JSONL)"
    )
    p_diff.add_argument(
        "--jsonl",
        action="store_true",
        help="Emit JSON lines instead of a single JSON array",
    )

    p_pre = sub.add_parser(
        "preprocess", help="Process Defects4J bugs and build method-level diff data"
    )
    p_pre.add_argument(
        "--projects",
        type=str,
        default="Lang,Chart,Time,Math,Mockito",
        help="Comma-separated list of D4J projects",
    )
    p_pre.add_argument(
        "--out",
        type=str,
        default="/root/d4j_data",
        help="Output directory for per-bug JSON files",
    )
    p_pre.add_argument(
        "--start-id",
        type=int,
        default=None,
        help="Start bug id (inclusive) to process for single project",
    )
    p_pre.add_argument(
        "--end-id",
        type=int,
        default=None,
        help="End bug id (inclusive) to process for single project",
    )
    p_pre.add_argument(
        "--project-only",
        type=str,
        default=None,
        help="If provided, limit to this single project name",
    )
    p_pre.add_argument(
        "--main-only",
        action="store_true",
        help="Scan only src/main/java subtrees when present",
    )
    p_pre.add_argument(
        "--force", action="store_true", help="Overwrite existing outputs"
    )
    p_pre.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop on first checkout/diff error instead of skipping",
    )
    p_pre.add_argument(
        "--jobs",
        type=int,
        default=(os.cpu_count() or 4),
        help="Number of parallel workers for preprocessing (1 disables parallelism)",
    )

    return p


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI."""
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
    if args.cmd == "diff":
        buggy_root = Path(args.buggy).resolve()
        fixed_root = Path(args.fixed).resolve()
        for p in (buggy_root, fixed_root):
            if not p.exists():
                print(f"Path not found: {p}", file=sys.stderr)
                return 2
        count = run_diff(buggy_root, fixed_root, out_path, args.jsonl)
        print(
            f"[OK] Extracted {count} methods (diff mode) from {buggy_root}",
            file=sys.stderr,
        )
        return 0
    if args.cmd == "preprocess":
        projects = [
            x.strip()
            for x in (args.project_only or args.projects).split(",")
            if x.strip()
        ]
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
    ap.print_help()
    return 2
