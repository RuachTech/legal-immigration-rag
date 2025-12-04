#!/usr/bin/env python3
"""Verify that the project structure and dependencies are correctly set up."""

import sys
from pathlib import Path


def check_directories():
    """Check that all required directories exist."""
    required_dirs = [
        "frontend/src/components",
        "frontend/src/hooks",
        "frontend/src/services",
        "frontend/src/types",
        "backend",
        "rag_pipeline/retrieval",
        "rag_pipeline/generation",
        "rag_pipeline/memory",
        "data_pipeline/scrapers",
        "data_pipeline/processing",
        "storage/vector",
        "storage/session",
        "evaluation/metrics",
        "evaluation/datasets",
        "evaluation/benchmarks",
        "tests/unit",
        "tests/integration",
        "tests/property",
        "scripts",
        "docs",
    ]
    
    missing = []
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing.append(dir_path)
    
    if missing:
        print("❌ Missing directories:")
        for d in missing:
            print(f"   - {d}")
        return False
    else:
        print("✓ All required directories exist")
        return True


def check_python_imports():
    """Check that core Python modules can be imported."""
    try:
        from storage import VectorStore, SessionStore, Chunk, ChunkMetadata
        from storage import Conversation, Message, Citation, Rationale
        print("✓ Storage interfaces can be imported")
        return True
    except ImportError as e:
        print(f"❌ Failed to import storage interfaces: {e}")
        return False


def check_files():
    """Check that key configuration files exist."""
    required_files = [
        "pyproject.toml",
        ".env.example",
        ".gitignore",
        "README.md",
        "frontend/package.json",
        "frontend/tsconfig.json",
        "frontend/vite.config.ts",
        "storage/vector/base.py",
        "storage/session/base.py",
    ]
    
    missing = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing.append(file_path)
    
    if missing:
        print("❌ Missing files:")
        for f in missing:
            print(f"   - {f}")
        return False
    else:
        print("✓ All required configuration files exist")
        return True


def main():
    """Run all verification checks."""
    print("Verifying project setup...\n")
    
    checks = [
        check_directories(),
        check_files(),
        check_python_imports(),
    ]
    
    print("\n" + "="*50)
    if all(checks):
        print("✓ Project setup verification passed!")
        print("\nNext steps:")
        print("1. Copy .env.example to .env and configure")
        print("2. Start implementing tasks from .kiro/specs/legal-immigration-rag/tasks.md")
        return 0
    else:
        print("❌ Project setup verification failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
