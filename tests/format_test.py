#!/usr/bin/env python3
"""Verify PDF and DOCX ingestion: same SOP in three formats must retrieve
the same answer with correct source attribution."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sop_mcp.store import Store
from sop_mcp.chunking import read_document

SAMPLES = os.path.join(ROOT, "tests", "format_samples")
DATA = os.path.abspath(os.path.join(ROOT, "..", "format_test_data"))

# 1. raw extraction check
for name in ("SOP-WH-005_Dispatch.pdf", "SOP-WH-005_Dispatch.docx"):
    text, err = read_document(os.path.join(SAMPLES, name))
    assert err is None, "%s: %s" % (name, err)
    assert "seal number" in text.lower(), "%s: seal text missing" % name
    assert "Version: 2.2" in text, "%s: version header missing" % name
    print("%s: extracted %d chars, version header found" % (name, len(text)))

# 2. retrieval check across all three formats
import shutil
shutil.rmtree(DATA, ignore_errors=True)
store = Store(DATA)
result = store.ingest_folder(SAMPLES)
assert result["total_documents"] == 3, result
print("ingested 3 formats, chunks: %d" % result["total_chunks"])

hits = store.search("what must be checked before dispatching goods?", top_k=3)
assert hits and hits[0]["doc_id"].startswith("SOP-WH-005_Dispatch"), hits[:1]
assert hits[0]["version"] == "2.2", hits[0]["version"]
print("top-1: %s (version %s, section: %s)" % (
    hits[0]["doc_id"], hits[0]["version"], hits[0]["section"]))

hits2 = store.search("vehicle seal number does not match, what now?", top_k=3)
assert hits2 and hits2[0]["doc_id"].startswith("SOP-WH-005_Dispatch")
print("seal query top-1 ok")

print("\nFORMAT SUPPORT: ALL CHECKS PASSED")
