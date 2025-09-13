# Defects4J Extractor

A Python tool for extracting Java method information and JavaDoc from source code trees using Tree-sitter. Designed specifically for analyzing Defects4J bug datasets and comparing buggy vs fixed code versions.

## Features

- **Method Extraction**: Parse Java source files and extract detailed method information including:
  - Fully qualified method names (package + class nesting + method)
  - Parameter types and names
  - Return types
  - Start/end line numbers and byte offsets
  - Complete method source code
  - Leading JavaDoc comments (normalized)

- **Diff Mode**: Compare buggy and fixed source trees to identify:
  - Modified methods (code or JavaDoc changes)
  - Added methods
  - Removed methods

- **Defects4J Integration**: Automated preprocessing of Defects4J bug datasets with:
  - Automatic bug checkout from Defects4J
  - Parallel processing support
  - Batch processing of multiple projects and bug IDs

## Installation

### Prerequisites

- Python 3.7+
- Defects4J (for preprocessing mode)

### Dependencies

Install required Python packages:

```bash
pip install tree-sitter tree-sitter-languages orjson
```

For Defects4J integration, ensure Defects4J is installed and available in your PATH:
```bash
# Verify Defects4J installation
defects4j info
```

## Usage

The tool provides three main commands: `scan`, `diff`, and `preprocess`.

### 1. Scan Mode - Extract Methods from Single Source Tree

Extract all methods from a Java source directory:

```bash
python defects4j_extractor.py scan /path/to/java/source --out methods.json
```

Output as JSON Lines:
```bash
python defects4j_extractor.py scan /path/to/java/source --jsonl --out methods.jsonl
```

### 2. Diff Mode - Compare Buggy vs Fixed Versions

Compare two source trees and extract only changed methods:

```bash
python defects4j_extractor.py diff /path/to/buggy/source /path/to/fixed/source --out changes.json
```

### 3. Preprocess Mode - Automated Defects4J Processing

Process multiple Defects4J projects automatically:

```bash
# Process all default projects (Lang, Chart, Time, Math, Mockito)
python defects4j_extractor.py preprocess --out /output/directory

# Process specific project with ID range
python defects4j_extractor.py preprocess --project-only Lang --start-id 1 --end-id 10 --out /output/directory

# Use parallel processing
python defects4j_extractor.py preprocess --jobs 4 --out /output/directory
```

## Command-Line Options

### Scan Command
```
python defects4j_extractor.py scan <source_directory> [options]
```
- `source_directory`: Path to Java source root directory
- `--out PATH`: Output file path (JSON or JSONL)
- `--jsonl`: Output as JSON Lines instead of single JSON array

### Diff Command
```
python defects4j_extractor.py diff <buggy_directory> <fixed_directory> [options]
```
- `buggy_directory`: Path to buggy source root
- `fixed_directory`: Path to fixed source root
- `--out PATH`: Output file path (JSON or JSONL)
- `--jsonl`: Output as JSON Lines instead of single JSON array

### Preprocess Command
```
python defects4j_extractor.py preprocess [options]
```
- `--projects`: Comma-separated list of D4J projects (default: "Lang,Chart,Time,Math,Mockito")
- `--project-only`: Process only this single project
- `--start-id INT`: Start bug ID (inclusive)
- `--end-id INT`: End bug ID (inclusive)
- `--out PATH`: Output directory (default: "/root/d4j_data")
- `--main-only`: Scan only src/main/java when present
- `--force`: Overwrite existing output files
- `--stop-on-error`: Stop on first error instead of skipping
- `--jobs INT`: Number of parallel workers (default: CPU count)

## Output Format

### Method Information (Scan Mode)

```json
{
  "file_path": "/path/to/Example.java",
  "package_name": "com.example",
  "class_qualifier": "Example$InnerClass",
  "method_name": "calculateSum",
  "parameters": ["int a", "int b"],
  "return_type": "int",
  "start_line": 25,
  "end_line": 30,
  "start_byte": 1024,
  "end_byte": 1200,
  "javadoc": "Calculates the sum of two integers.\n@param a first integer\n@param b second integer\n@return sum of a and b",
  "code": "public int calculateSum(int a, int b) {\n    return a + b;\n}"
}
```

### Diff Information (Diff/Preprocess Mode)

```json
{
  "status": "modified",
  "signature": {
    "file_rel_path": "src/main/java/Example.java",
    "class_qualifier": "Example",
    "method_name": "buggyMethod",
    "arity": 2
  },
  "buggy": {
    // Complete MethodInfo object for buggy version
  },
  "fixed": {
    // Complete MethodInfo object for fixed version
  }
}
```

Status values:
- `"modified"`: Method exists in both versions but code/JavaDoc changed
- `"added"`: Method only exists in fixed version
- `"removed"`: Method only exists in buggy version

## Examples

### Extract methods from Apache Commons Lang

```bash
# Download and extract Lang project
git clone https://github.com/apache/commons-lang.git
python defects4j_extractor.py scan commons-lang/src/main/java --out lang_methods.json
```

### Compare buggy vs fixed version using Defects4J

```bash
# Manual checkout and comparison
defects4j checkout -p Lang -v 1b -w /tmp/lang_1_buggy
defects4j checkout -p Lang -v 1f -w /tmp/lang_1_fixed
python defects4j_extractor.py diff /tmp/lang_1_buggy /tmp/lang_1_fixed --out lang_1_diff.json
```

### Automated processing of specific bugs

```bash
# Process Lang bugs 1-50 with 8 parallel workers
python defects4j_extractor.py preprocess \
    --project-only Lang \
    --start-id 1 \
    --end-id 50 \
    --jobs 8 \
    --out ./lang_dataset
```

## Technical Details

- **Parser**: Uses Tree-sitter with Java grammar for robust parsing
- **Method Detection**: Identifies method declarations and constructors
- **JavaDoc Extraction**: Finds and normalizes leading `/** ... */` comments
- **Nested Classes**: Handles inner classes with `$` separator notation
- **Error Handling**: Continues processing on parse errors, logging warnings
- **Performance**: Supports parallel processing for large-scale extraction

## Limitations

- Requires valid Java syntax (compilation not required)
- JavaDoc extraction uses heuristic matching (may miss some edge cases)
- Parameter type extraction is best-effort based on tokens
- Does not resolve complex generic types or imports

## Contributing

The tool is designed to be extensible. Key areas for enhancement:
- Additional output formats
- More sophisticated type resolution
- Support for other JVM languages
- Integration with build systems

## License

This tool is designed for research and analysis of Java codebases, particularly in the context of software defect analysis and program repair research.
