"""Document registry and index store."""
import hashlib
import json
import os

from . import chunking, versions
from .retrieval import BM25Index


def _ver_tuple(v):
    try:
        return tuple(int(p) for p in v.split("."))
    except Exception:
        return (0,)


class Store:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.manifest_path = os.path.join(data_dir, "manifest.json")
        self.docs = {}       # doc_id -> meta
        self.index = BM25Index()
        self._load()

    # ---------- persistence ----------
    def _load(self):
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self.docs = json.load(f)
            except Exception:
                self.docs = {}
        self._rebuild()

    def _save(self):
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.docs, f, indent=2, ensure_ascii=False)

    def _rebuild(self):
        index = BM25Index()
        for doc_id, meta in list(self.docs.items()):
            path = meta["path"]
            chunks, err = chunking.build_chunks(path, doc_id)
            if err or not chunks:
                # file moved/deleted: drop from registry
                self.docs.pop(doc_id, None)
                continue
            for c in chunks:
                c["family"] = meta["family"]
                c["version"] = meta["version"]
                c["version_tuple"] = _ver_tuple(meta["version"])
            index.add_chunks(chunks)
            meta["chunks"] = len(chunks)
        self.index = index
        self._save()

    # ---------- operations ----------
    def ingest_folder(self, folder):
        added, skipped, errors = [], [], []
        if not os.path.isdir(folder):
            return {"error": "folder not found: %s" % folder}
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            doc_id = name  # full filename incl. extension: same SOP in
            # .pdf and .docx must not overwrite each other
            with open(path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()[:12]
            if doc_id in self.docs and self.docs[doc_id].get("sha") == sha:
                skipped.append(doc_id)
                continue
            text, err = chunking.read_document(path)
            if err or text is None:
                errors.append({"file": name, "error": err})
                continue
            meta = {
                "path": os.path.abspath(path),
                "sha": sha,
                "family": versions.doc_family(name),
                "version": versions.extract_version(text, name),
                "effective_date": versions.extract_effective_date(text),
                "supersedes": versions.extract_supersedes(text),
            }
            self.docs[doc_id] = meta
            added.append(doc_id)
        self._rebuild()
        return {
            "added": added,
            "skipped_unchanged": skipped,
            "errors": errors,
            "total_documents": len(self.docs),
            "total_chunks": len(self.index.chunks),
        }

    def remove_document(self, doc_id):
        if doc_id in self.docs:
            self.docs.pop(doc_id)
            self._rebuild()
            return {"removed": doc_id}
        return {"error": "unknown document: %s" % doc_id}

    def version_boost(self):
        boost = {}
        for meta in self.docs.values():
            fam = meta["family"]
            t = _ver_tuple(meta["version"])
            if fam not in boost or t > boost[fam]:
                boost[fam] = t
        return boost

    def search(self, query, top_k=5):
        return self.index.search(query, top_k=top_k,
                                 version_boost=self.version_boost())

    def conflicts(self):
        return versions.find_conflicts(self.docs)

    def list_documents(self):
        return [
            {
                "doc_id": d,
                "version": m["version"],
                "effective_date": m.get("effective_date"),
                "sections": m.get("chunks"),
                "file": os.path.basename(m["path"]),
            }
            for d, m in sorted(self.docs.items())
        ]
