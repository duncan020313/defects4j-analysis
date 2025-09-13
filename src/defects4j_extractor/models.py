"""
Data models for the Defects4J extractor.
"""

from __future__ import annotations

import dataclasses
from typing import List, Optional


@dataclasses.dataclass
class MethodInfo:
    """Information about a Java method extracted from source code."""

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
        """Get the fully qualified name of the method."""
        parts: List[str] = []
        if self.package_name:
            parts.append(self.package_name)
        if self.class_qualifier:
            parts.append(self.class_qualifier)
        parts.append(self.method_name)
        return ".".join(p for p in parts if p)


@dataclasses.dataclass
class StackTraceElement:
    """Information about a single stack trace element."""
    
    class_name: str
    method_name: str
    file_name: Optional[str]
    line_number: Optional[int]
    
    @property
    def fully_qualified_method(self) -> str:
        """Get the fully qualified method name."""
        return f"{self.class_name}.{self.method_name}"


@dataclasses.dataclass
class TriggeringTestInfo:
    """Information about a test that triggers a bug."""

    test_method: str
    test_class: str
    exception_class: Optional[str]
    exception_message: Optional[str]
    source_code: Optional[str]
    stack_trace: Optional[List[StackTraceElement]] = None
    raw_stack_trace: Optional[str] = None


@dataclasses.dataclass
class BugMetadata:
    """Metadata about a Defects4J bug."""

    project_id: str
    bug_id: int
    revision_id_buggy: str
    revision_id_fixed: str
    classes_modified: List[str]
    triggering_tests: List[TriggeringTestInfo]
    relevant_tests: List[str]
