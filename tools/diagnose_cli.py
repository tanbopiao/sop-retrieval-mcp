"""SOP Diagnostic: health-check a document repository and produce a
diagnosis report. Read-only over the customer's files; the report contains
no document text — only filenames, versions, statistics and advice.

Usage:
    python tools/diagnose_cli.py <folder> [--report-dir DIR] [--stale-months N]
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sop_mcp import versions
from sop_mcp.chunking import read_document, split_sections
from sop_mcp.retrieval import BM25Index
from sop_mcp.store import Store

# ---------------------------------------------------------------------------
# Built-in coverage probes: common warehouse operations topics. Each probe
# is a (topic label, list of query phrasings). A topic is "covered" when at
# least one phrasing retrieves a chunk scoring above COVERAGE_MIN_SCORE.
# ---------------------------------------------------------------------------
COVERAGE_PROBES = [
    ("Receiving / inbound goods", [
        "receiving inbound goods procedure",
        "what to check when goods arrive at the dock",
        "delivery vehicle arrival check",
    ]),
    ("Putaway / storage", [
        "where to store goods after receiving putaway",
        "putaway system entry procedure",
        "storage location assignment",
    ]),
    ("Picking / order fulfilment", [
        "order picking procedure warehouse",
        "how to pick items for an order",
        "pick list process",
    ]),
    ("Packing", [
        "packing procedure before shipping",
        "how to pack cartons for dispatch",
        "packing station checks",
    ]),
    ("Dispatch / shipping", [
        "what must be checked before dispatching goods",
        "loading vehicle dispatch procedure",
        "outbound shipment checks",
    ]),
    ("Returns / reverse logistics", [
        "customer returns procedure",
        "how to handle returned goods",
        "return authorisation process",
    ]),
    ("Damage handling", [
        "damaged goods handling procedure",
        "what to do with damaged cartons",
        "damaged stock reporting",
    ]),
    ("Cold chain / temperature", [
        "temperature check chilled frozen goods",
        "cold chain monitoring procedure",
        "temperature excursion what to do",
    ]),
    ("Inventory count / stock accuracy", [
        "stock count cycle count procedure",
        "inventory accuracy check",
        "stock discrepancy investigation",
    ]),
    ("Safety / incident reporting", [
        "workplace safety incident reporting",
        "accident in warehouse what to do",
        "safety incident escalation",
    ]),
]

COVERAGE_MIN_SCORE = 1.0   # BM25 score below this counts as "no hit"
DEFAULT_STALE_MONTHS = 18  # effective date older than this = stale


def _ver_tuple(v):
    try:
        return tuple(int(p) for p in str(v).split("."))
    except Exception:
        return (0,)


def _parse_effective_date(s):
    """Parse 'YYYY-MM-DD' or 'Month DD, YYYY' into a date, else None."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})$", s)
    if m:
        try:
            return datetime.datetime.strptime(
                "%s %s %s" % (m.group(1), m.group(2), m.group(3)),
                "%B %d %Y").date()
        except ValueError:
            return None
    return None


def _months_ago(d, now):
    return (now - d).days / 30.44


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_metadata(docs):
    """Missing version / effective date / document number per document."""
    findings = []
    for doc_id, meta in sorted(docs.items()):
        missing = []
        if not meta.get("version") or meta.get("version") == "1.0":
            # 1.0 is the fallback default when nothing was found
            missing.append("version number (not detected in text or filename)")
        if not meta.get("effective_date"):
            missing.append("effective date")
        m = re.match(r"^(SOP|WI|SOP-|WI-)?[-_ ]?([A-Z]{2,}[-_]?\d+)", doc_id.upper())
        if not re.search(r"\d", doc_id):
            missing.append("document number/ID (filename has no number)")
        if missing:
            findings.append({
                "type": "missing_metadata",
                "severity": "medium",
                "document": os.path.basename(meta.get("path", doc_id)),
                "missing": missing,
                "advice": "Add the missing fields to the document header "
                          "(e.g. 'Version: 2.1', 'Effective Date: 2026-01-15'). "
                          "Retrieval and version control both rely on them.",
            })
    return findings


def check_stale(docs, now, stale_months):
    """Documents whose effective date is older than the threshold."""
    findings = []
    for doc_id, meta in sorted(docs.items()):
        d = _parse_effective_date(meta.get("effective_date"))
        if d is None:
            continue
        age = _months_ago(d, now)
        if age >= stale_months:
            findings.append({
                "type": "stale_document",
                "severity": "medium",
                "document": os.path.basename(meta.get("path", doc_id)),
                "effective_date": meta.get("effective_date"),
                "age_months": round(age),
                "advice": "This document has not been updated in %d months. "
                          "Review it against current practice; if still valid, "
                          "re-issue with a new effective date." % round(age),
            })
    return findings


def check_supersedes_chain(docs):
    """Supersedes links that point outside the loaded set (broken chain)."""
    loaded = set()
    for doc_id, meta in docs.items():
        loaded.add((meta["family"], str(meta.get("version"))))
    findings = []
    for doc_id, meta in sorted(docs.items()):
        sup = meta.get("supersedes")
        if not sup:
            continue
        m = re.search(r"v?(\d+(?:\.\d+)+)", str(sup))
        if not m:
            continue
        prev_ver = m.group(1)
        fam = meta["family"]
        if (fam, prev_ver) not in loaded:
            findings.append({
                "type": "supersedes_chain_gap",
                "severity": "low",
                "document": os.path.basename(meta.get("path", doc_id)),
                "supersedes": str(sup)[:80],
                "advice": "This document supersedes version %s, which is not "
                          "in the loaded set. If the older file still exists "
                          "somewhere, retire it to keep one source of truth."
                          % prev_ver,
            })
    return findings


def check_coverage(docs, index, version_boost):
    """Probe common operations topics; report weak/missing coverage."""
    findings = []
    for topic, queries in COVERAGE_PROBES:
        best_score = 0.0
        best_doc = None
        for q in queries:
            for c in index.search(q, top_k=3, version_boost=version_boost):
                if c["score"] > best_score:
                    best_score = c["score"]
                    best_doc = c["doc_id"]
        if best_score < COVERAGE_MIN_SCORE:
            findings.append({
                "type": "coverage_gap",
                "severity": "high" if best_score < COVERAGE_MIN_SCORE / 2 else "medium",
                "topic": topic,
                "best_score": round(best_score, 2),
                "best_document": best_doc,
                "advice": "No strong match found for the topic '%s'. Either "
                          "the procedure does not exist in the library, or it "
                          "is written in terms too different from everyday "
                          "language. Operators asking about this topic will "
                          "not find approved guidance." % topic,
            })
    return findings


def check_retrieval_sample(docs, index, version_boost, samples=5):
    """Self-test: run representative questions, report top hits and scores."""
    test_questions = [
        "What must be checked before dispatching goods?",
        "What do I do if the vehicle seal number does not match?",
        "Where do damaged cartons go during putaway?",
        "How do I handle a customer return?",
        "What temperature is safe for chilled goods?",
    ]
    out = []
    for q in test_questions[:samples]:
        hits = index.search(q, top_k=2, version_boost=version_boost)
        out.append({
            "question": q,
            "top_hits": [{
                "document": h["doc_id"],
                "version": h.get("version"),
                "section": h.get("section"),
                "score": h["score"],
            } for h in hits],
            "top_score": hits[0]["score"] if hits else 0.0,
        })
    return out


def check_version_conflicts(docs):
    """Reuse engine conflict detection (same family, multiple versions)."""
    return versions.find_conflicts(docs)


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def run_diagnosis(folder, data_dir=None, stale_months=DEFAULT_STALE_MONTHS,
                  now=None):
    now = now or datetime.date.today()
    data_dir = data_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data")
    store = Store(data_dir)
    ingest = store.ingest_folder(folder)
    if ingest.get("error"):
        raise SystemExit("Cannot read folder: %s" % ingest["error"])

    docs = store.docs
    index = store.index
    boost = store.version_boost()

    findings = []
    findings.extend(check_version_conflicts(docs))
    findings.extend(check_metadata(docs))
    findings.extend(check_stale(docs, now, stale_months))
    findings.extend(check_supersedes_chain(docs))
    findings.extend(check_coverage(docs, index, boost))
    retrieval_sample = check_retrieval_sample(docs, index, boost)

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: severity_rank.get(f.get("severity"), 3))

    report = {
        "generated_at": now.isoformat(),
        "folder": os.path.abspath(folder),
        "documents_scanned": len(docs),
        "ingest_errors": ingest.get("errors", []),
        "summary": {
            "high": sum(1 for f in findings if f.get("severity") == "high"),
            "medium": sum(1 for f in findings if f.get("severity") == "medium"),
            "low": sum(1 for f in findings if f.get("severity") == "low"),
            "total": len(findings),
        },
        "findings": findings,
        "retrieval_self_test": retrieval_sample,
        "note": "This report contains no document text — only filenames, "
                "versions, statistics and recommendations. It is safe to "
                "share back with us for a solution proposal.",
    }
    return report


def to_markdown(report):
    lines = []
    lines.append("# SOP Repository Diagnosis Report")
    lines.append("")
    lines.append("Generated: %s  |  Documents scanned: %d" % (
        report["generated_at"], report["documents_scanned"]))
    if report["ingest_errors"]:
        lines.append("")
        lines.append("**Files that could not be read:** %s" % ", ".join(
            e["file"] for e in report["ingest_errors"]))
    s = report["summary"]
    lines.append("")
    lines.append("## Summary: %d finding(s) — %d high, %d medium, %d low" % (
        s["total"], s["high"], s["medium"], s["low"]))
    lines.append("")
    if not report["findings"]:
        lines.append("No issues detected by the built-in checks. "
                     "The library looks healthy.")
    for f in report["findings"]:
        sev = f.get("severity", "info").upper()
        title = f.get("topic") or f.get("document") or f.get("family") or f["type"]
        lines.append("### [%s] %s — %s" % (sev, f["type"], title))
        detail = {k: v for k, v in f.items()
                  if k not in ("type", "severity", "advice")}
        for k, v in detail.items():
            lines.append("- %s: %s" % (k, v))
        lines.append("- **Advice:** %s" % f.get("advice", ""))
        lines.append("")
    lines.append("## Retrieval self-test")
    lines.append("")
    lines.append("Representative questions and where the engine points:")
    lines.append("")
    for t in report["retrieval_self_test"]:
        top = t["top_hits"][0] if t["top_hits"] else None
        if top:
            lines.append("- \"%s\" → %s (v%s, score %.2f)" % (
                t["question"], top["document"], top.get("version"),
                t["top_score"]))
        else:
            lines.append("- \"%s\" → no hit" % t["question"])
    lines.append("")
    lines.append("---")
    lines.append(report["note"])
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Diagnose a SOP document repository (read-only)")
    ap.add_argument("folder", help="Folder containing your SOP documents")
    ap.add_argument("--data-dir", default=None,
                    help="Working directory for the local index (default: ./data)")
    ap.add_argument("--report-dir", default=None,
                    help="Where to write the report (default: same as data-dir)")
    ap.add_argument("--stale-months", type=int, default=DEFAULT_STALE_MONTHS,
                    help="Documents with effective date older than this many "
                         "months are flagged as stale (default: %d)"
                         % DEFAULT_STALE_MONTHS)
    args = ap.parse_args()

    report = run_diagnosis(args.folder, data_dir=args.data_dir,
                           stale_months=args.stale_months)

    report_dir = args.report_dir or args.data_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(report_dir, exist_ok=True)
    json_path = os.path.join(report_dir, "diagnosis_report.json")
    md_path = os.path.join(report_dir, "diagnosis_report.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(report))

    print("Diagnosis complete: %d document(s) scanned, %d finding(s) "
          "[high %d / medium %d / low %d]" % (
              report["documents_scanned"], report["summary"]["total"],
              report["summary"]["high"], report["summary"]["medium"],
              report["summary"]["low"]))
    print("Report written to:")
    print("  %s" % os.path.abspath(json_path))
    print("  %s" % os.path.abspath(md_path))
    print("Safe to share: the report contains no document text.")


if __name__ == "__main__":
    main()
