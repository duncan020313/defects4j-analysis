# Defects4J Analysis Suite

A comprehensive toolkit for extracting, analyzing, and browsing Java method-level changes from Defects4J bug datasets. This project combines a powerful extraction tool with an interactive web interface for exploring software defects and their fixes.

## 🚀 Quick Start

```bash
# 1. Clone and setup
git clone <repository-url>
cd defects4j-analysis
pip install -r requirements.txt

# 2. Extract Defects4J data (requires Defects4J installation)
python src/defects4j_extractor.py preprocess --out ./data --projects Lang,Chart

# 3. Start the web server to browse results
cd server
pip install -r requirements.txt
D4J_DATA_DIR=../data uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Open http://localhost:8000 in your browser
```

## 📁 Repository Structure

```
defects4j-analysis/
├── README.md                 # This file - main project documentation
├── requirements.txt          # Core dependencies
├── src/
│   └── defects4j_extractor.py # Main extraction tool
├── server/                   # Web interface for browsing data
│   ├── main.py              # FastAPI server
│   ├── requirements.txt     # Server dependencies
│   ├── static/
│   │   └── index.html       # Web UI
│   └── README.md           # Server-specific documentation
├── docs/
│   └── extractor_readme.md  # Detailed extractor documentation
├── examples/                # Usage examples and sample scripts
├── scripts/                # Utility scripts for common tasks
└── data/                   # Default output directory (created by extraction)
```

## 🔧 Components

### 1. Defects4J Extractor (`src/defects4j_extractor.py`)

A powerful Python tool that uses Tree-sitter to parse Java source code and extract detailed method information.

**Key Features:**
- **Method Extraction**: Complete method signatures, parameters, return types, JavaDoc
- **Diff Analysis**: Compare buggy vs fixed versions to identify changes
- **Batch Processing**: Automated processing of entire Defects4J dataset
- **Parallel Processing**: Multi-threaded extraction for large datasets

**Usage Modes:**
```bash
# Extract all methods from a source tree
python src/defects4j_extractor.py scan /path/to/java/source --out methods.json

# Compare buggy vs fixed versions
python src/defects4j_extractor.py diff /path/to/buggy /path/to/fixed --out changes.json

# Batch process Defects4J projects
python src/defects4j_extractor.py preprocess --projects Lang,Chart,Time,Math,Mockito --out ./data
```

### 2. Web Browser (`server/`)

Interactive FastAPI-based web interface for exploring extracted method data.

**Features:**
- Project and bug navigation
- Full-text search across code, JavaDoc, and signatures
- Side-by-side diff viewing with syntax highlighting
- REST API for programmatic access

**API Endpoints:**
- `GET /api/projects` - List available projects
- `GET /api/bugs?project=Lang` - List bugs for a project
- `GET /api/bug/{project}/{bug_id}/details` - Detailed method changes
- `GET /api/search?q=searchterm` - Full-text search

## 📋 Prerequisites

### Core Requirements
- **Python 3.7+**
- **Defects4J** (for data extraction)

### For Defects4J Integration
```bash
# Install Defects4J (one-time setup)
git clone https://github.com/rjust/defects4j.git
cd defects4j
./init.sh
export PATH=$PATH:$(pwd)/framework/bin

# Verify installation
defects4j info
```

## 🛠 Installation

### Option 1: Basic Setup
```bash
# Install core dependencies
pip install -r requirements.txt

# For web server (optional)
cd server
pip install -r requirements.txt
```

### Option 2: Development Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
cd server && pip install -r requirements.txt
```

## 📖 Usage Examples

### Extract Methods from a Single Project

```bash
# Download Apache Commons Lang
git clone https://github.com/apache/commons-lang.git

# Extract all methods
python src/defects4j_extractor.py scan commons-lang/src/main/java --out lang_methods.json

# View extraction stats
echo "Extracted $(jq length lang_methods.json) methods"
```

### Process Specific Defects4J Bugs

```bash
# Process first 10 Lang bugs with 4 parallel workers
python src/defects4j_extractor.py preprocess \
    --project-only Lang \
    --start-id 1 \
    --end-id 10 \
    --jobs 4 \
    --out ./lang_subset

# Process multiple projects
python src/defects4j_extractor.py preprocess \
    --projects "Lang,Chart,Time" \
    --main-only \
    --out ./defects4j_data
```

### Launch Web Interface

```bash
# Set data directory and start server
export D4J_DATA_DIR=/path/to/extracted/data
cd server
uvicorn main:app --host 0.0.0.0 --port 8000

# Or use a different port
uvicorn main:app --port 8080
```

### Search and Analysis

```bash
# Search via API
curl "http://localhost:8000/api/search?q=StringUtils&project=Lang"

# Get bug details
curl "http://localhost:8000/api/bug/Lang/1/details"

# List all projects
curl "http://localhost:8000/api/projects"
```

## 🔍 Output Format

### Method Information
```json
{
  "file_path": "/path/to/Example.java",
  "package_name": "org.apache.commons.lang3",
  "class_qualifier": "StringUtils",
  "method_name": "isEmpty",
  "parameters": ["CharSequence cs"],
  "return_type": "boolean",
  "start_line": 142,
  "end_line": 144,
  "javadoc": "Checks if a CharSequence is empty...",
  "code": "public static boolean isEmpty(final CharSequence cs) {\n    return cs == null || cs.length() == 0;\n}"
}
```

### Diff Information
```json
{
  "status": "modified",
  "signature": {
    "file_rel_path": "src/main/java/org/apache/commons/lang3/StringUtils.java",
    "class_qualifier": "StringUtils",
    "method_name": "isEmpty",
    "arity": 1
  },
  "buggy": { /* MethodInfo for buggy version */ },
  "fixed": { /* MethodInfo for fixed version */ }
}
```

## 🎯 Common Use Cases

### 1. Bug Pattern Analysis
Extract and analyze common bug patterns across projects:
```bash
# Extract all bugs for analysis
python src/defects4j_extractor.py preprocess --out ./analysis_data

# Use web interface to search for specific patterns
# e.g., "null check", "array bounds", "string comparison"
```

### 2. Method-Level Diff Research
Study specific types of changes:
```bash
# Process specific projects
python src/defects4j_extractor.py preprocess --projects "Math,Lang" --out ./research_data

# Use API to filter by change type
curl "http://localhost:8000/api/search?q=return"
```

### 3. Dataset Creation
Create training data for ML models:
```bash
# Extract comprehensive dataset
python src/defects4j_extractor.py preprocess \
    --projects "Lang,Chart,Time,Math,Mockito,Cli,Codec,Collections,Compress,Csv,Gson,JacksonCore,JacksonDatabind,JacksonXml,Jsoup,JxPath" \
    --main-only \
    --force \
    --jobs 8 \
    --out ./ml_dataset
```

## 🤝 Contributing

We welcome contributions! Areas for enhancement:

- **Additional Parsers**: Support for Kotlin, Scala, other JVM languages
- **Enhanced Analysis**: Type resolution, dependency analysis
- **Export Formats**: CSV, XML, database integration
- **Visualization**: Charts, graphs, statistical analysis
- **Performance**: Caching, indexing, streaming for large datasets

## 📚 Documentation

- **[Extractor Documentation](docs/extractor_readme.md)** - Detailed extractor usage and options
- **[Server Documentation](server/README.md)** - Web interface and API reference

## ⚠️ Limitations

- Requires valid Java syntax (compilation not required)
- JavaDoc extraction uses heuristic matching
- Parameter type extraction is best-effort
- Does not resolve complex generics or perform semantic analysis

## 📄 License

This project is designed for research and analysis of Java codebases, particularly in software defect analysis and program repair research.

## 🔗 Related Projects

- [Defects4J](https://github.com/rjust/defects4j) - The original bug dataset
- [Tree-sitter](https://tree-sitter.github.io/) - Parser generator used for Java analysis
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework for the browser interface

---

**Happy Bug Hunting! 🐛🔍**
