"""
Command-line interface for the Defects4J extractor.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .defects4j import preprocess_project
from .extractor import run_diff, run_scan

console = Console()


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
            console.print(f"[red]Error:[/red] Source root not found: {source_root}")
            return 2
        
        console.print(Panel(
            f"[cyan]Scanning Java source tree[/cyan]\n"
            f"Source: {source_root}\n"
            f"Output: {out_path or 'stdout'}\n"
            f"Format: {'JSONL' if args.jsonl else 'JSON'}",
            title="[bold blue]Defects4J Extractor - Scan Mode[/bold blue]"
        ))
        
        with console.status("[bold green]Extracting methods..."):
            count = run_scan(source_root, out_path, args.jsonl)
        
        console.print(f"[green]✓[/green] Extracted {count} methods from {source_root}")
        return 0
        
    if args.cmd == "diff":
        buggy_root = Path(args.buggy).resolve()
        fixed_root = Path(args.fixed).resolve()
        for p in (buggy_root, fixed_root):
            if not p.exists():
                console.print(f"[red]Error:[/red] Path not found: {p}")
                return 2
        
        console.print(Panel(
            f"[cyan]Comparing buggy and fixed source trees[/cyan]\n"
            f"Buggy: {buggy_root}\n"
            f"Fixed: {fixed_root}\n"
            f"Output: {out_path or 'stdout'}\n"
            f"Format: {'JSONL' if args.jsonl else 'JSON'}",
            title="[bold blue]Defects4J Extractor - Diff Mode[/bold blue]"
        ))
        
        with console.status("[bold green]Computing method differences..."):
            count = run_diff(buggy_root, fixed_root, out_path, args.jsonl)
        
        console.print(f"[green]✓[/green] Extracted {count} changed methods")
        return 0
        
    if args.cmd == "preprocess":
        projects = [
            x.strip()
            for x in (args.project_only or args.projects).split(",")
            if x.strip()
        ]
        out_dir = Path(args.out).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        
        console.print(Panel(
            f"[cyan]Preprocessing Defects4J projects[/cyan]\n"
            f"Projects: {', '.join(projects)}\n"
            f"Output directory: {out_dir}\n"
            f"ID range: {args.start_id or 'auto'} to {args.end_id or 'auto'}\n"
            f"Main source only: {args.main_only}\n"
            f"Force overwrite: {args.force}\n"
            f"Parallel jobs: {getattr(args, 'jobs', 1)}",
            title="[bold blue]Defects4J Extractor - Preprocess Mode[/bold blue]"
        ))
        
        total = 0
        for proj in projects:
            console.print(f"\n[bold cyan]Processing project: {proj}[/bold cyan]")
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
        
        console.print(f"\n[green]✓[/green] Preprocessed {total} bug(s) into {out_dir}")
        return 0
        
    ap.print_help()
    return 2
