#!/usr/bin/env python3
"""
Basic usage examples for the Defects4J extractor.

This script demonstrates common usage patterns and API interactions.
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import defects4j_extractor as extractor
except ImportError:
    print("❌ Could not import defects4j_extractor")
    print("Make sure you're running from the repository root")
    sys.exit(1)


def example_scan_directory():
    """Example: Scan a Java source directory."""
    print("📁 Example: Scanning a directory")
    
    # This would scan a real Java directory
    # source_path = Path("/path/to/java/source")
    # if source_path.exists():
    #     parser = extractor.load_java_parser()
    #     methods = []
    #     for java_file in extractor.iter_java_files(source_path):
    #         file_methods = extractor.extract_from_file(parser, java_file)
    #         methods.extend(file_methods)
    #     print(f"Found {len(methods)} methods")
    
    print("   (Skipped - no source directory provided)")


def example_process_single_file():
    """Example: Process a single Java file."""
    print("📄 Example: Processing a single file")
    
    # Create a sample Java file
    sample_java = '''
package com.example;

/**
 * A simple calculator class.
 */
public class Calculator {
    
    /**
     * Adds two integers.
     * @param a first number
     * @param b second number  
     * @return sum of a and b
     */
    public int add(int a, int b) {
        return a + b;
    }
    
    public int multiply(int a, int b) {
        return a * b;
    }
}
'''
    
    # Write to temporary file
    temp_file = Path("/tmp/Calculator.java")
    temp_file.write_text(sample_java)
    
    try:
        parser = extractor.load_java_parser()
        methods = extractor.extract_from_file(parser, temp_file)
        
        print(f"   Found {len(methods)} methods:")
        for method in methods:
            print(f"   - {method.fully_qualified_name} ({len(method.parameters)} params)")
            if method.javadoc:
                print(f"     JavaDoc: {method.javadoc[:50]}...")
    
    finally:
        temp_file.unlink(missing_ok=True)


def example_api_usage():
    """Example: Using the web API programmatically."""
    print("🌐 Example: API usage")
    print("   # List projects")
    print("   curl http://localhost:8000/api/projects")
    print()
    print("   # Search for methods")
    print("   curl 'http://localhost:8000/api/search?q=StringUtils&project=Lang'")
    print()
    print("   # Get bug details")
    print("   curl 'http://localhost:8000/api/bug/Lang/1/details'")


def main():
    print("🔧 Defects4J Extractor - Basic Usage Examples")
    print("=" * 50)
    
    example_scan_directory()
    print()
    
    example_process_single_file()
    print()
    
    example_api_usage()
    print()
    
    print("✅ Examples complete!")
    print()
    print("Next steps:")
    print("1. Run the setup script: ./scripts/setup.sh")
    print("2. Extract sample data: ./scripts/extract_sample.sh")
    print("3. Start the web server and explore the UI")


if __name__ == "__main__":
    main()
