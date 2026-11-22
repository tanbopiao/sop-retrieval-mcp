"""Pure-Python BM25 retrieval over document chunks. No external deps."""
import math
import re
from .chunking import tokenize

K1 = 1.5
B = 0.75


class BM25Index:
    def __init__(self):
        self.chunks = []          # list of chunk dicts
        self.doc_freq = {}        # token -> number of chunks containing it
        self.avg_len = 1.0
        self._tf = []             # per-chunk term freq dicts
        self._len = []

    def add_chunks(self, chunks):
        for c in chunks:
            idx = len(self.chunks)
            tokens = tokenize(c["text"])
            tf = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self._tf.append(tf)
            self._len.append(len(tokens))
            for t in tf:
                self.doc_freq[t] = self.doc_freq.get(t, 0) + 1
            c["_idx"] = idx
            self.chunks.append(c)
        self._finalize()

    def _finalize(self):
        total = sum(self._len) or 1
        self.avg_len = total / max(len(self.chunks), 1)

    def _idf(self, token):
        n = len(self.chunks)
        df = self.doc_freq.get(token, 0)
        if df == 0:
            return 0.0
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def search(self, query, top_k=5, version_boost=None, max_per_doc=2):
        """Return top_k chunk dicts with scores and surrounding context.
        If version_boost is a dict {family: max_version_tuple}, chunks from
        lower versions of the same family are penalized so the latest
        procedure ranks first."""
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = {}
        seen = set()
        for qt in q_tokens:
            if qt in seen:
                continue
            seen.add(qt)
            idf = self._idf(qt)
            if idf <= 0:
                continue
            for idx, tf in enumerate(self._tf):
                f = tf.get(qt, 0)
                if not f:
                    continue
                dl = self._len[idx] or 1
                s = idf * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / self.avg_len))
                scores[idx] = scores.get(idx, 0.0) + s
        # phrase bonus: exact multi-word phrase match
        q_lower = " " + re.sub(r"\s+", " ", query.lower()).strip() + " "
        results = []
        for idx, s in scores.items():
            text = self.chunks[idx]["text"].lower()
            if len(q_tokens) > 2 and q_lower.strip() in text:
                s *= 1.6
            if version_boost:
                fam = self.chunks[idx].get("family")
                ver = self.chunks[idx].get("version_tuple", (0,))
                max_ver = version_boost.get(fam)
                if max_ver and ver < max_ver:
                    s *= 0.45   # outdated version penalty
            results.append((s, idx))
        results.sort(key=lambda x: -x[0])
        # diversity: at most max_per_doc chunks from the same document
        out = []
        per_doc = {}
        for s, idx in results:
            doc = self.chunks[idx]["doc_id"]
            if per_doc.get(doc, 0) >= max_per_doc:
                continue
            per_doc[doc] = per_doc.get(doc, 0) + 1
            c = dict(self.chunks[idx])
            c["score"] = round(s, 4)
            c.pop("_idx", None)
            out.append(c)
            if len(out) >= top_k:
                break
        # context expansion: attach neighbouring chunks of the same document
        for c in out:
            neighbors = []
            for c2 in self.chunks:
                if c2["doc_id"] == c["doc_id"] and c2["text"] != c["text"]:
                    neighbors.append(c2["text"])
            c["context"] = "\n---\n".join(neighbors[:4])
        return out
