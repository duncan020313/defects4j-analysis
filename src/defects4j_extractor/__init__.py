"""
Defects4J extractor package for analyzing Java method changes.
"""

from .cli import build_arg_parser, main
from .defects4j import preprocess_project
from .extractor import run_diff, run_scan
from .models import BugMetadata, MethodInfo, TriggeringTestInfo
from .parser import extract_from_file, iter_java_files, load_java_parser

__all__ = [
    "MethodInfo",
    "TriggeringTestInfo",
    "BugMetadata",
    "load_java_parser",
    "extract_from_file",
    "iter_java_files",
    "run_scan",
    "run_diff",
    "preprocess_project",
    "build_arg_parser",
    "main",
]
