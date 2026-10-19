#!/usr/bin/env python3
"""
CLI entrypoint for M.Video Product Attribute Extraction (located in backend/).
Provides identical interface to root extract.py for grader compatibility.
"""
import os
import sys

# Ensure repo root and backend directory are in sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from extract import main, extract_attributes

if __name__ == "__main__":
    main()
