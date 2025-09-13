## d4j_server

FastAPI server and minimal UI to browse Defects4J method-level changes produced by `defects4j_extractor.py`.

### Features
- List projects and bugs available in the local dataset
- Full-text search across class names, method names, JavaDoc, and code
- View per-bug details with JavaDoc and patch diffs (buggy vs fixed)

### Prerequisites
- Python 3.8+
- Dependencies are included in the main project dependencies (run `uv sync` from project root)

### Data directory
Set the dataset path via `D4J_DATA_DIR` (defaults to `/root/d4j_data`). Files are expected to be JSON files named like `Lang_1.json`, each containing the output of `defects4j_extractor.py diff`/`preprocess`.

To build the dataset:
```bash
uv run python src/defects4j_extractor.py preprocess --out /root/d4j_data --projects Lang,Chart,Time,Math,Mockito --main-only
```

### Run the server
```bash
export D4J_DATA_DIR=/root/d4j_data
uv run uvicorn server.main:app --host 0.0.0.0 --port 8000
```
Open `http://localhost:8000` to use the UI.

### REST API
- `GET /api/projects`: List available project names
- `GET /api/bugs?project=Lang`: List bug IDs for a project
- `GET /api/all_bugs[?project=Lang]`: List all bugs (project, bug_id, method counts)
- `GET /api/bug/{project}/{bug_id}/methods`: Raw method records for a bug
- `GET /api/bug/{project}/{bug_id}/details`: Method records with JavaDoc and unified diffs
- `GET /api/search?q=... [&project=Lang] [&limit=50]`: Search across dataset

### Notes
- The UI is a single static page in `static/index.html` served by FastAPI.
- Unified diffs are generated on demand; large bugs may take a moment to render.


