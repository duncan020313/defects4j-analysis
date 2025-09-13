from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import difflib

import orjson
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import ORJSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


def orjson_dumps(v, *, default):
    return orjson.dumps(v, default=default)


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.projects: Dict[str, Dict[int, Dict[str, Any]]] = {}
        # Load all {Project}_{id}.json files
        self._load()

    def _load(self) -> None:
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
        for p in sorted(self.data_dir.glob("*.json")):
            name = p.name
            m = re.match(r"^([A-Za-z]+)_(\d+)\.json$", name)
            if not m:
                continue
            project = m.group(1)
            bug_id = int(m.group(2))
            try:
                content = orjson.loads(p.read_bytes())
            except Exception:
                # Fall back to std json
                content = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            self.projects.setdefault(project, {})[bug_id] = {
                "path": str(p),
                "records": content,
            }

    def list_projects(self) -> List[str]:
        return sorted(self.projects.keys())

    def list_bugs(self, project: str) -> List[int]:
        return sorted(self.projects.get(project, {}).keys())

    def bug_methods(self, project: str, bug_id: int) -> List[Dict[str, Any]]:
        proj = self.projects.get(project)
        if not proj or bug_id not in proj:
            raise KeyError
        records = proj[bug_id]["records"]
        # Handle both old format (list of methods) and new format (dict with bug_metadata + changed_methods)
        if isinstance(records, list):
            return records
        else:
            return records.get("changed_methods", [])
    
    def bug_metadata(self, project: str, bug_id: int) -> Optional[Dict[str, Any]]:
        proj = self.projects.get(project)
        if not proj or bug_id not in proj:
            raise KeyError
        records = proj[bug_id]["records"]
        # Handle both old format (list of methods) and new format (dict with bug_metadata + changed_methods)
        if isinstance(records, dict):
            return records.get("bug_metadata")
        return None

    def list_all_bugs(self, project: Optional[str] = None) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        projects = [project] if project else sorted(self.projects.keys())
        for prj in projects:
            for bug_id, data in self.projects.get(prj, {}).items():
                records = data.get("records") or []
                # Handle both old format (list of methods) and new format (dict with bug_metadata + changed_methods)
                if isinstance(records, list):
                    method_count = len(records)
                else:
                    method_count = len(records.get("changed_methods", []))
                
                rows.append({
                    "project": prj,
                    "bug_id": bug_id,
                    "method_count": method_count,
                })
        rows.sort(key=lambda r: (r["project"], r["bug_id"]))
        return rows

    def search(self, q: str, project: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        ql = q.lower().strip()
        if not ql:
            return []
        results: List[Dict[str, Any]] = []
        projects = [project] if project else list(self.projects.keys())
        for prj in projects:
            for bug_id, data in self.projects.get(prj, {}).items():
                records = data["records"]
                # Handle both old format (list of methods) and new format (dict with bug_metadata + changed_methods)
                if isinstance(records, list):
                    methods = records
                else:
                    methods = records.get("changed_methods", [])
                
                for rec in methods:
                    sig = rec.get("signature", {})
                    file_rel_path = (sig.get("file_rel_path") or "").lower()
                    class_qualifier = (sig.get("class_qualifier") or "").lower()
                    method_name = (sig.get("method_name") or "").lower()
                    # Search in both sides if present
                    texts: List[str] = [file_rel_path, class_qualifier, method_name]
                    for side in ("buggy", "fixed"):
                        side_rec = rec.get(side)
                        if side_rec:
                            texts.append((side_rec.get("javadoc") or "").lower())
                            texts.append((side_rec.get("code") or "").lower())
                    hay = "\n".join(texts)
                    if ql in hay:
                        results.append({
                            "project": prj,
                            "bug_id": bug_id,
                            "status": rec.get("status"),
                            "signature": rec.get("signature"),
                        })
                        if len(results) >= limit:
                            return results
        return results


DATA_DIR = Path(os.environ.get("D4J_DATA_DIR", "/root/d4j_data")).resolve()
store = DataStore(DATA_DIR)

app = FastAPI(default_response_class=ORJSONResponse)


@app.get("/api/projects")
def api_projects() -> List[str]:
    return store.list_projects()


@app.get("/api/bugs")
def api_bugs(project: str = Query(...)) -> List[int]:
    bugs = store.list_bugs(project)
    if not bugs:
        raise HTTPException(status_code=404, detail="Project not found or no bugs")
    return bugs


@app.get("/api/all_bugs")
def api_all_bugs(project: Optional[str] = None) -> List[Dict[str, Any]]:
    return store.list_all_bugs(project)


@app.get("/api/bug/{project}/{bug_id}/methods")
def api_bug_methods(project: str, bug_id: int) -> List[Dict[str, Any]]:
    try:
        return store.bug_methods(project, bug_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bug not found")


@app.get("/api/bug/{project}/{bug_id}/metadata")
def api_bug_metadata(project: str, bug_id: int) -> Dict[str, Any]:
    try:
        metadata = store.bug_metadata(project, bug_id)
        if metadata is None:
            return {}
        return metadata
    except KeyError:
        raise HTTPException(status_code=404, detail="Bug not found")


def _unified_diff(a: str, b: str, from_label: str, to_label: str) -> str:
    a_lines = (a or "").splitlines(keepends=True)
    b_lines = (b or "").splitlines(keepends=True)
    # Use full-context diff to always show whole method bodies
    n = max(len(a_lines), len(b_lines))
    diff_iter = difflib.unified_diff(
        a_lines,
        b_lines,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
        n=n,
    )
    return "\n".join(diff_iter)


@app.get("/api/bug/{project}/{bug_id}/details")
def api_bug_details(project: str, bug_id: int) -> Dict[str, Any]:
    try:
        records = store.bug_methods(project, bug_id)
        metadata = store.bug_metadata(project, bug_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bug not found")

    details: List[Dict[str, Any]] = []
    for rec in records:
        buggy = rec.get("buggy") or {}
        fixed = rec.get("fixed") or {}
        code_buggy = buggy.get("code") or ""
        code_fixed = fixed.get("code") or ""
        javadoc_buggy = buggy.get("javadoc") or ""
        javadoc_fixed = fixed.get("javadoc") or ""

        code_diff = _unified_diff(code_buggy, code_fixed, "buggy/code", "fixed/code")
        javadoc_diff = _unified_diff(javadoc_buggy, javadoc_fixed, "buggy/javadoc", "fixed/javadoc")

        details.append({
            "status": rec.get("status"),
            "signature": rec.get("signature"),
            "javadoc_buggy": javadoc_buggy,
            "javadoc_fixed": javadoc_fixed,
            "code_buggy": code_buggy,
            "code_fixed": code_fixed,
            "code_diff": code_diff,
            "javadoc_diff": javadoc_diff,
        })
    
    return {
        "bug_metadata": metadata or {},
        "changed_methods": details
    }


@app.get("/api/search")
def api_search(q: str = Query(...), project: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    return store.search(q, project, limit)


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


