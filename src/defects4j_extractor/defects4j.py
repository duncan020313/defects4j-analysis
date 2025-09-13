"""
Defects4J integration functionality for bug preprocessing and metadata extraction.
"""

from __future__ import annotations

import dataclasses
import functools
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import orjson
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .models import BugMetadata, MethodInfo, TriggeringTestInfo, StackTraceElement
from .parser import (
    extract_from_file,
    find_package_name,
    iter_java_files,
    load_java_parser,
    read_text_bytes,
    walk_methods,
)

console = Console()


def _run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Execute a command and return exit code, stdout, stderr."""
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = proc.communicate()
    return proc.returncode, out, err


def _defects4j_bug_ids(project: str) -> List[int]:
    """Query available active bug ids via defects4j info -p <proj>."""
    console.print(f"[dim]Querying active bug IDs for project {project}...[/dim]")
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
    console.print(f"[dim]Found {len(ids)} active bug IDs for project {project}[/dim]")
    return sorted(set(ids))


def _get_active_bug_ids(project: str) -> Set[int]:
    """Get all active bug IDs for a project from Defects4J."""
    code, out, err = _run_cmd([
        "defects4j", "query", "-p", project, "-q", "bug.id"
    ])
    if code != 0:
        return set()
    
    active_ids = set()
    for line in out.splitlines():
        line = line.strip()
        # Skip header line
        if line.startswith("bug.id") or line.startswith("Bug.ID") or not line:
            continue
        try:
            active_ids.add(int(line))
        except ValueError:
            continue
    return active_ids


def _is_active_bug(project: str, bug_id: int, active_bugs: Optional[Set[int]] = None) -> bool:
    """Check if a bug is active (not deprecated) in Defects4J."""
    if active_bugs is None:
        active_bugs = _get_active_bug_ids(project)
    return bug_id in active_bugs


def _query_bug_metadata(project: str, bug_id: int) -> BugMetadata:
    """Use defects4j query to get detailed bug information."""
    console.print(f"[dim]Querying metadata for {project}-{bug_id}...[/dim]")
    cmd = [
        "defects4j",
        "query",
        "-p",
        project,
        "-q",
        "bug.id,revision.id.buggy,revision.id.fixed,classes.modified,tests.trigger,tests.trigger.cause,tests.relevant",
    ]
    code, out, err = _run_cmd(cmd)
    if code != 0:
        raise RuntimeError(f"defects4j query failed for {project}-{bug_id}: {err}")

    # Parse the CSV-like output - defects4j query returns CSV format without headers
    lines = out.strip().split("\n")
    if not lines:
        raise RuntimeError(f"No query output for {project}-{bug_id}")

    # Find the data line for our bug
    data_line = None
    for line in lines:
        if line.strip().startswith(str(bug_id) + ","):
            data_line = line.strip()
            break

    if not data_line:
        raise RuntimeError(f"Bug {bug_id} not found in query results for {project}")

    # Parse the CSV line - we know the column order from our query
    # Columns: bug.id,revision.id.buggy,revision.id.fixed,classes.modified,tests.trigger,tests.trigger.cause,tests.relevant
    try:
        # Handle CSV parsing for lines with potential quoted fields containing commas
        import csv
        import io
        reader = csv.reader(io.StringIO(data_line))
        values = next(reader)
    except:
        # Fallback to simple split if CSV parsing fails
        values = data_line.split(",")

    if len(values) < 7:
        raise RuntimeError(f"Unexpected query output format for {project}-{bug_id}: expected 7 columns, got {len(values)}")

    # Map values to field names
    data = {
        "bug.id": values[0].strip(),
        "revision.id.buggy": values[1].strip(),
        "revision.id.fixed": values[2].strip(),
        "classes.modified": values[3].strip(),
        "tests.trigger": values[4].strip(),
        "tests.trigger.cause": values[5].strip(),
        "tests.relevant": values[6].strip(),
    }

    # Extract triggering tests information
    triggering_tests = []
    if "tests.trigger.cause" in data and data["tests.trigger.cause"]:
        # Format: "methodName --> exceptionClass[: message]" separated by semicolons
        for trigger_info in data["tests.trigger.cause"].split(";"):
            trigger_info = trigger_info.strip()
            if not trigger_info:
                continue

            # Parse "methodName --> exceptionClass[: message]"
            if " --> " in trigger_info:
                test_method, exception_info = trigger_info.split(" --> ", 1)
                test_method = test_method.strip()

                # Extract test class from method (usually ClassName::methodName format)
                if "::" in test_method:
                    test_class, method_name = test_method.rsplit("::", 1)
                else:
                    # Fallback: try to extract from method name patterns
                    test_class = ""
                    method_name = test_method

                # Parse exception info
                exception_class = None
                exception_message = None
                if ":" in exception_info:
                    exception_class, exception_message = exception_info.split(":", 1)
                    exception_class = exception_class.strip()
                    exception_message = exception_message.strip()
                else:
                    exception_class = exception_info.strip()

                triggering_tests.append(
                    TriggeringTestInfo(
                        test_method=method_name,
                        test_class=test_class,
                        exception_class=exception_class,
                        exception_message=exception_message,
                        source_code=None,  # Will be populated later
                    )
                )
    elif "tests.trigger" in data and data["tests.trigger"]:
        # Fallback to simpler format if tests.trigger.cause not available
        for test_method in data["tests.trigger"].split(";"):
            test_method = test_method.strip()
            if not test_method:
                continue

            if "::" in test_method:
                test_class, method_name = test_method.rsplit("::", 1)
            else:
                test_class = ""
                method_name = test_method

            triggering_tests.append(
                TriggeringTestInfo(
                    test_method=method_name,
                    test_class=test_class,
                    exception_class=None,
                    exception_message=None,
                    source_code=None,
                )
            )

    # Extract relevant tests
    relevant_tests = []
    if "tests.relevant" in data and data["tests.relevant"]:
        relevant_tests = [
            t.strip() for t in data["tests.relevant"].split(";") if t.strip()
        ]

    # Extract modified classes
    modified_classes = []
    if "classes.modified" in data and data["classes.modified"]:
        modified_classes = [
            c.strip() for c in data["classes.modified"].split(";") if c.strip()
        ]

    return BugMetadata(
        project_id=project,
        bug_id=bug_id,
        revision_id_buggy=data.get("revision.id.buggy", ""),
        revision_id_fixed=data.get("revision.id.fixed", ""),
        classes_modified=modified_classes,
        triggering_tests=triggering_tests,
        relevant_tests=relevant_tests,
    )


def _parse_stack_trace(raw_trace: str) -> List[StackTraceElement]:
    """Parse a Java stack trace into StackTraceElement objects."""
    stack_elements = []
    
    for line in raw_trace.split('\n'):
        line = line.strip()
        if not line or not line.startswith('at '):
            continue
            
        # Remove 'at ' prefix
        line = line[3:].strip()
        
        # Parse pattern like: "com.example.Class.method(Class.java:123)"
        # or "com.example.Class.method(Unknown Source)"
        # or "com.example.Class.method(Native Method)"
        if '(' in line and line.endswith(')'):
            method_part, location_part = line.rsplit('(', 1)
            location_part = location_part[:-1]  # Remove closing parenthesis
            
            # Extract class and method
            if '.' in method_part:
                class_name, method_name = method_part.rsplit('.', 1)
            else:
                class_name = ""
                method_name = method_part
            
            # Extract file and line number
            file_name = None
            line_number = None
            
            if location_part not in ['Unknown Source', 'Native Method']:
                if ':' in location_part:
                    file_name, line_str = location_part.rsplit(':', 1)
                    try:
                        line_number = int(line_str)
                    except ValueError:
                        line_number = None
                else:
                    file_name = location_part
                    
            stack_elements.append(StackTraceElement(
                class_name=class_name,
                method_name=method_name,
                file_name=file_name,
                line_number=line_number
            ))
    
    return stack_elements


def _run_failing_test(project: str, bug_id: int, test_class: str, test_method: str, checkout_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    """Run a specific failing test and capture its output including stack traces."""
    console.print(f"[dim]Running failing test {test_class}::{test_method} for {project}-{bug_id}...[/dim]")
    
    # Use defects4j test command to run specific test
    cmd = [
        "defects4j",
        "test",
        "-t", f"{test_class}::{test_method}"
    ]
    
    try:
        code, out, err = _run_cmd(cmd, cwd=checkout_dir)
        
        # Combine stdout and stderr to capture all test output
        full_output = f"{out}\n{err}".strip()
        
        # Extract stack trace - look for exception patterns
        exception_output = None
        raw_stack_trace = None
        
        lines = full_output.split('\n')
        for i, line in enumerate(lines):
            # Look for exception class names followed by colon or stack trace patterns
            if ('Exception' in line or 'Error' in line) and (':' in line or 'at ' in lines[i+1:i+10] if i+1 < len(lines) else False):
                # Found start of exception, capture everything until end or next test
                exception_lines = []
                for j in range(i, len(lines)):
                    current_line = lines[j]
                    # Stop if we hit another test or compilation output
                    if any(marker in current_line.lower() for marker in ['running', 'tests run:', '--- end of']):
                        break
                    exception_lines.append(current_line)
                    
                exception_output = '\n'.join(exception_lines).strip()
                raw_stack_trace = exception_output
                break
                
        return exception_output, raw_stack_trace
        
    except Exception as e:
        console.print(f"[red]Error running test {test_class}::{test_method}: {e}[/red]")
        return None, None


def _enhance_triggering_tests_with_stack_traces(project: str, bug_id: int, triggering_tests: List[TriggeringTestInfo], checkout_dir: Path) -> None:
    """Enhance triggering test info with detailed stack traces."""
    if not triggering_tests:
        return
        
    console.print(f"[dim]Collecting stack traces for {len(triggering_tests)} triggering tests...[/dim]")
    
    for test_info in triggering_tests:
        if not test_info.test_class or not test_info.test_method:
            continue
            
        exception_output, raw_stack_trace = _run_failing_test(
            project, bug_id, test_info.test_class, test_info.test_method, checkout_dir
        )
        
        if raw_stack_trace:
            test_info.raw_stack_trace = raw_stack_trace
            test_info.stack_trace = _parse_stack_trace(raw_stack_trace)
            
            # Update exception info if we got better data from running the test
            if exception_output and not test_info.exception_message:
                first_line = exception_output.split('\n')[0].strip()
                if ':' in first_line:
                    exc_class, exc_msg = first_line.split(':', 1)
                    test_info.exception_class = exc_class.strip()
                    test_info.exception_message = exc_msg.strip()
                elif 'Exception' in first_line or 'Error' in first_line:
                    test_info.exception_class = first_line.strip()


def _checkout_bug(project: str, bug_id: int, dest: Path, fixed: bool) -> None:
    """Checkout a specific bug version using defects4j."""
    version = f"{bug_id}{'f' if fixed else 'b'}"
    version_type = "fixed" if fixed else "buggy"
    console.print(f"[dim]Checking out {version_type} version of {project}-{bug_id}...[/dim]")
    code, out, err = _run_cmd(
        ["defects4j", "checkout", "-p", project, "-v", version, "-w", str(dest)]
    )
    if code != 0:
        raise RuntimeError(f"defects4j checkout failed: {project}-{version}: {err}")


def _source_root_for_checkout(workdir: Path, main_only: bool) -> Path:
    """Find the appropriate source root for a checked out project."""
    # Prefer src/main/java if present and main_only requested, else workdir
    candidate = workdir / "src" / "main" / "java"
    if main_only and candidate.exists():
        return candidate
    return workdir


def _test_root_for_checkout(workdir: Path) -> Optional[Path]:
    """Find test source root - common patterns in Java projects."""
    candidates = [
        workdir / "src" / "test" / "java",
        workdir / "test",
        workdir / "tests",
        workdir / "src" / "test",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _extract_test_method_code(
    parser, test_root: Path, triggering_tests: List[TriggeringTestInfo]
) -> None:
    """Extract source code for triggering test methods."""
    console.print(f"[dim]Extracting test method code for {len(triggering_tests)} triggering tests...[/dim]")
    # Build a map from test class name to potential file paths
    class_to_files: Dict[str, List[Path]] = {}

    for java_file in iter_java_files(test_root):
        # Extract simple class name from file path
        file_stem = java_file.stem
        if not class_to_files.get(file_stem):
            class_to_files[file_stem] = []
        class_to_files[file_stem].append(java_file)

        # Also try to extract from package structure
        try:
            text_str, data = read_text_bytes(java_file)
            tree = parser.parse(data)
            root = tree.root_node
            package_name = find_package_name(root, data)

            # Find class declarations
            for method_info in walk_methods(
                root, data, text_str, package_name, str(java_file)
            ):
                if method_info.class_qualifier:
                    # Use the full class qualifier as a potential match
                    class_key = method_info.class_qualifier.split("$")[
                        0
                    ]  # Handle inner classes
                    if not class_to_files.get(class_key):
                        class_to_files[class_key] = []
                    if java_file not in class_to_files[class_key]:
                        class_to_files[class_key].append(java_file)
        except Exception:
            # Skip files that can't be parsed
            continue

    # Now find the specific test methods
    for test_info in triggering_tests:
        if test_info.source_code is not None:
            continue  # Already populated

        # Try to find the test class file
        potential_files = []

        # Try exact test class name
        if test_info.test_class:
            class_name = test_info.test_class.split(".")[
                -1
            ]  # Get last part of qualified name
            if class_name in class_to_files:
                potential_files.extend(class_to_files[class_name])

        # Also try searching all files for the method name as fallback
        if not potential_files:
            potential_files = [f for files in class_to_files.values() for f in files]

        # Search for the test method in potential files
        for java_file in potential_files:
            try:
                text_str, data = read_text_bytes(java_file)
                tree = parser.parse(data)
                root = tree.root_node
                package_name = find_package_name(root, data)

                for method_info in walk_methods(
                    root, data, text_str, package_name, str(java_file)
                ):
                    if method_info.method_name == test_info.test_method:
                        # Check if this is likely the right class
                        if (
                            not test_info.test_class
                            or test_info.test_class.endswith(
                                method_info.class_qualifier
                            )
                            or method_info.class_qualifier.endswith(
                                test_info.test_class.split(".")[-1]
                            )
                        ):
                            test_info.source_code = method_info.code
                            break

                if test_info.source_code:
                    break  # Found it, stop searching

            except Exception:
                # Skip files that can't be parsed
                continue


def preprocess_project(
    project: str,
    out_dir: Path,
    start_id: Optional[int],
    end_id: Optional[int],
    main_only: bool,
    force: bool,
    stop_on_error: bool = False,
    jobs: int = 1,
) -> int:
    """Process Defects4J bugs and build method-level diff data."""
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

    console.print(f"[bold]Processing {len(ids)} bugs for project {project}[/bold]")
    console.print(f"Bug IDs: {ids[:10]}{'...' if len(ids) > 10 else ''}")
    console.print(f"Parallel jobs: {jobs}, Force overwrite: {force}")
    console.print()

    # Get active bugs list once to avoid repeated queries
    console.print(f"[dim]Getting active bugs list for {project}...[/dim]")
    active_bugs = _get_active_bug_ids(project)
    console.print(f"[dim]Found {len(active_bugs)} active bugs total[/dim]")
    
    # Filter to only active bugs
    active_ids = [bug_id for bug_id in ids if bug_id in active_bugs]
    skipped_count = len(ids) - len(active_ids)
    if skipped_count > 0:
        console.print(f"[dim]Silently skipping {skipped_count} deprecated bug(s)[/dim]")
    
    # Update ids to only process active bugs
    ids = active_ids
    
    if not ids:
        console.print(f"[yellow]⚠[/yellow] No active bugs to process for {project}")
        return 0

    # Normalize jobs
    jobs = int(jobs) if isinstance(jobs, int) else 1
    if jobs < 1:
        jobs = 1

    # Create a partial function for parallel processing that binds the parameters
    process_func = functools.partial(
        _process_one_bug_impl,
        project=project,
        out_dir=out_dir,
        main_only=main_only,
        force=force,
        stop_on_error=stop_on_error,
    )

    # Fallback to sequential if requested to stop on first error or single worker
    if stop_on_error or jobs == 1:
        processed = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Processing {project} bugs", total=len(ids))
            for bug_id in ids:
                progress.update(task, description=f"Processing {project}-{bug_id}")
                processed += process_func(bug_id)
                progress.advance(task)
        return processed

    # For parallel processing, use a simpler progress indicator since we can't easily track individual tasks
    console.print(f"[bold]Starting parallel processing with {jobs} workers...[/bold]")
    processed = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Processing {project} bugs (parallel)", total=len(ids))
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            completed = 0
            for result in executor.map(process_func, ids):
                processed += int(result or 0)
                completed += 1
                progress.update(task, completed=completed)
    return processed


def _process_one_bug_impl(
    bug_id: int,
    project: str,
    out_dir: Path,
    main_only: bool,
    force: bool,
    stop_on_error: bool,
) -> int:
    """Process a single bug - moved to module level for multiprocessing compatibility."""
    out_path = out_dir / f"{project}_{bug_id}.json"
    if out_path.exists() and not force:
        # Skip existing
        return 0
    
    try:
        # Query the bug metadata to get triggering tests
        try:
            bug_metadata = _query_bug_metadata(project, bug_id)
        except Exception as meta_ex:
            console.print(
                f"[red]✗[/red] {project}-{bug_id}: Failed to query metadata: {meta_ex}"
            )
            bug_metadata = None

        with tempfile.TemporaryDirectory(prefix=f"d4j_{project}_{bug_id}_") as tmpd:
            tmp = Path(tmpd)
            buggy = tmp / "buggy"
            fixed = tmp / "fixed"
            _checkout_bug(project, bug_id, buggy, fixed=False)
            _checkout_bug(project, bug_id, fixed, fixed=True)
            buggy_src = _source_root_for_checkout(buggy, main_only)
            fixed_src = _source_root_for_checkout(fixed, main_only)

            # Extract test method code if we have bug metadata
            if bug_metadata and bug_metadata.triggering_tests:
                console.print(f"[dim]Processing {len(bug_metadata.triggering_tests)} triggering tests...[/dim]")
                parser = load_java_parser()
                # Try to find test code in buggy version first, then fixed if not found
                buggy_test_root = _test_root_for_checkout(buggy)
                if buggy_test_root:
                    _extract_test_method_code(
                        parser, buggy_test_root, bug_metadata.triggering_tests
                    )

                # If some tests still don't have source code, try fixed version
                missing_code_tests = [
                    t for t in bug_metadata.triggering_tests if not t.source_code
                ]
                if missing_code_tests:
                    console.print(f"[dim]Trying fixed version for {len(missing_code_tests)} missing test methods...[/dim]")
                    fixed_test_root = _test_root_for_checkout(fixed)
                    if fixed_test_root:
                        _extract_test_method_code(
                            parser, fixed_test_root, missing_code_tests
                        )
                
                # Enhance with detailed stack traces by running the failing tests
                _enhance_triggering_tests_with_stack_traces(
                    project, bug_id, bug_metadata.triggering_tests, buggy
                )

            # Run diff and collect results
            console.print(f"[dim]Computing method-level diff for {project}-{bug_id}...[/dim]")
            parser = load_java_parser()

            def _normalize_code_for_diff(code: str) -> str:
                return re.sub(r"\s+", "", code)

            def _signature_tuple(
                file_rel_path: str, m: MethodInfo
            ) -> Tuple[str, str, str, int]:
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

            buggy_pairs = extract_with_rel(buggy_src)
            fixed_pairs = extract_with_rel(fixed_src)

            buggy_map: Dict[Tuple[str, str, str, int], MethodInfo] = {
                k: v for k, v in buggy_pairs
            }
            fixed_map: Dict[Tuple[str, str, str, int], MethodInfo] = {
                k: v for k, v in fixed_pairs
            }

            all_keys: Set[Tuple[str, str, str, int]] = set(buggy_map.keys()) | set(
                fixed_map.keys()
            )

            diff_results = []
            for key in sorted(all_keys):
                b = buggy_map.get(key)
                f = fixed_map.get(key)
                status: str
                if b and f:
                    code_changed = _normalize_code_for_diff(
                        b.code
                    ) != _normalize_code_for_diff(f.code)
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
                diff_results.append(rec)

            # Create final output with bug metadata
            final_output = {
                "bug_metadata": dataclasses.asdict(bug_metadata)
                if bug_metadata
                else None,
                "changed_methods": diff_results,
            }

            # Write to output file
            out_path.write_bytes(
                orjson.dumps(final_output, option=orjson.OPT_INDENT_2)
            )

            test_count = len(bug_metadata.triggering_tests) if bug_metadata else 0
            console.print(
                f"[green]✓[/green] {project}-{bug_id}: {len(diff_results)} changed method(s), {test_count} triggering test(s)"
            )
            return 1
    except RuntimeError as ex:
        msg = str(ex)
        if "deprecated bug" in msg.lower() or "deprecated" in msg.lower():
            # Silently skip deprecated bugs without logging
            return 0
        console.print(f"[red]✗[/red] {project}-{bug_id}: {msg}")
        if stop_on_error:
            raise
        return 0
    except Exception as ex:
        console.print(f"[red]✗[/red] {project}-{bug_id}: {ex}")
        if stop_on_error:
            raise
        return 0
