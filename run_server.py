#!/usr/bin/env python3
"""One-click start: run the SOP retrieval MCP server over stdio."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sop_mcp.server import main

if __name__ == "__main__":
    main()
