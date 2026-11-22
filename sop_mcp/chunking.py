"""Document loading and chunking for SOP retrieval."""
import os
import re
import hashlib
import json

CHUNK_TARGET = 700          # characters per chunk (soft target)
CHUNK_OVERLAP = 120

SECTION_RE = re.compile(r"^(#{1,4}\s+.+|[A-Z][A-Z0-9 \-/&,()]{4,80}:?)\s*$")


def _read_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "PDF support requires: pip install pypdf"
    try:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages), None
    except Exception as e:
        return None, "pdf read failed: %s" % e


def _read_docx(path):
    try:
        import docx
    except ImportError:
        return None, "DOCX support requires: pip install python-docx"
    try:
        d = docx.Document(path)
        parts = []
        for para in d.paragraphs:
            parts.append(para.text)
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts), None
    except Exception as e:
        return None, "docx read failed: %s" % e


def read_document(path):
    """Read a document as plain text. Supports .txt, .md, .csv, .json,
    .log, .pdf and .docx. Returns (text, error) tuple."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext not in (".txt", ".md", ".csv", ".json", ".log"):
        return None, "unsupported type: %s" % ext
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), None
    except OSError as e:
        return None, str(e)


def split_sections(text):
    """Split text into (section_title, section_text) pairs using markdown
    headings or ALL-CAPS section lines as boundaries."""
    lines = text.splitlines()
    sections = []
    cur_title = "(front matter)"
    cur = []
    for line in lines:
        if SECTION_RE.match(line.strip()) and len(line.strip()) < 90:
            if cur:
                sections.append((cur_title, "\n".join(cur)))
            cur_title = line.strip().lstrip("#").strip()
            cur = []
        else:
            cur.append(line)
    if cur:
        sections.append((cur_title, "\n".join(cur)))
    return sections


def chunk_text(text, target=CHUNK_TARGET, overlap=CHUNK_OVERLAP):
    """Split a block of text into overlapping chunks on sentence boundaries."""
    text = text.strip()
    if not text:
        return []
    # split into sentences-ish units
    units = re.split(r"(?<=[.!?;])\s+|\n+", text)
    units = [u.strip() for u in units if u.strip()]
    chunks = []
    buf = ""
    for u in units:
        if buf and len(buf) + len(u) + 1 > target:
            chunks.append(buf)
            buf = buf[-overlap:] + " " + u if overlap < len(buf) else u
        else:
            buf = (buf + " " + u).strip() if buf else u
    if buf:
        chunks.append(buf)
    return chunks


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return _TOKEN_RE.findall(text.lower())


def build_chunks(doc_path, doc_id):
    """Build retrieval chunks for one document.
    Returns list of chunk dicts with text, section, position."""
    text, err = read_document(doc_path)
    if err or text is None:
        return None, err
    chunks = []
    for sec_title, sec_text in split_sections(text):
        for i, piece in enumerate(chunk_text(sec_text)):
            chunks.append({
                "doc_id": doc_id,
                "section": sec_title,
                "part": i + 1,
                "text": piece,
            })
    return chunks, None
