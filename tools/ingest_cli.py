#!/usr/bin/env python3
"""One-command ingestion: load a folder of SOP files and print a summary.

Usage:
    python tools/ingest_cli.py <folder> [--data-dir DIR]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sop_mcp.store import Store
from sop_mcp import trial


def main():
    ap = argparse.ArgumentParser(description="Ingest SOP documents")
    ap.add_argument("folder")
    ap.add_argument("--data-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    args = ap.parse_args()

    lic = trial.check_trial(args.data_dir)
    print("Trial: %s" % lic["message"])
    if not lic["ok"]:
        sys.exit(1)

    store = Store(args.data_dir)
    result = store.ingest_folder(args.folder)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    conflicts = store.conflicts()
    if conflicts:
        print("\nVersion conflicts detected:")
        for c in conflicts:
            print(" - %s: versions %s (%s)" % (
                c["family"], ", ".join(c["versions"]),
                ", ".join(c["documents"])))
    print("\nDone. Start the MCP server with: python run_server.py")


if __name__ == "__main__":
    main()
