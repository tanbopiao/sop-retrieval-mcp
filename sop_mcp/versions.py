"""Version metadata extraction and conflict detection."""
import os
import re

VERSION_PATTERNS = [
    re.compile(r"\bversion[:\s]*v?(\d+(?:\.\d+)+)", re.I),
    re.compile(r"\brev(?:ision)?[:\s]*v?(\d+(?:\.\d+)+)", re.I),
    re.compile(r"\bv(\d+(?:\.\d+)+)\b"),
]
EFFECTIVE_RE = re.compile(
    r"effective\s+(?:date)?[:\s]*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})", re.I)
SUPERSEDES_RE = re.compile(r"supersedes?[:\s]*(.+)", re.I)


def extract_version(text, filename):
    """Best-effort version string from document text or filename."""
    head = text[:3000]
    for pat in VERSION_PATTERNS:
        m = pat.search(head)
        if m:
            return m.group(1)
    m = re.search(r"v(\d+(?:\.\d+)+)", filename, re.I)
    if m:
        return m.group(1)
    return "1.0"


def extract_effective_date(text):
    m = EFFECTIVE_RE.search(text[:3000])
    return m.group(1) if m else None


def extract_supersedes(text):
    m = SUPERSEDES_RE.search(text[:3000])
    return m.group(1).strip()[:120] if m else None


def doc_family(filename):
    """Normalize a filename to a document family key, stripping version
    markers so that SOP_v2.1.docx and SOP_v3.0.docx group together."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = re.sub(r"[_\-\s]*v\d+(\.\d+)*$", "", stem, flags=re.I)
    stem = re.sub(r"[_\-\s]*(rev|version|draft)\d*$", "", stem, flags=re.I)
    return stem.lower().strip("_- ")


def find_conflicts(docs):
    """Given registry of docs {doc_id: meta}, return list of conflict dicts:
    same family with multiple versions, or explicit supersedes warnings."""
    families = {}
    for doc_id, meta in docs.items():
        fam = meta["family"]
        families.setdefault(fam, []).append((doc_id, meta))
    conflicts = []
    for fam, members in families.items():
        versions = sorted({m["version"] for _, m in members})
        # same procedure in multiple formats with identical version is not
        # a conflict (likely the same document saved twice)
        if len(members) > 1 and len(versions) > 1:
            conflicts.append({
                "family": fam,
                "type": "multiple_versions",
                "documents": [d for d, _ in members],
                "versions": versions,
                "advice": "Multiple versions of this procedure are loaded. "
                          "search_procedure returns the highest version by default; "
                          "remove outdated files to avoid operator confusion.",
            })
    return conflicts
