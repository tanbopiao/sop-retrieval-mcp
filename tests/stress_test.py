#!/usr/bin/env python3
"""Stress test: generate a large synthetic SOP corpus where every document
carries a UNIQUE fact (its own form code), then measure whether retrieval
finds the right document and the right fact among near-duplicates."""
import json
import os
import random
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sop_mcp.store import Store

random.seed(7)

CORPUS_DIR = os.path.abspath(os.path.join(ROOT, "..", "stress_corpus"))

SITES = ["Panchkula", "Zirakpur", "Mohali", "Chandigarh", "Ambala", "Rajpura"]
DEPTS = ["Receiving", "Putaway", "Picking", "Packing", "Dispatch", "Returns",
         "ColdChain", "Inventory", "Sanitation", "Maintenance", "Safety",
         "Transport", "Quality", "Pest", "Training", "Waste"]
TOPICS = [
    ("vehicle seal number", "verify the vehicle seal against the ASN before unloading"),
    ("temperature excursion", "record the temperature reading before loading begins"),
    ("damaged cartons", "label damaged cartons with a red tag and photograph them"),
    ("short pick", "mark the line short and notify planning, do not substitute"),
    ("product recall", "quarantine affected stock immediately and notify quality"),
    ("pest sighting", "log the sighting and place a trap within 24 hours"),
    ("chemical spill", "use the spill kit and ventilate the area before cleaning"),
    ("forklift inspection", "complete the pre-use checklist before the first shift"),
    ("label mismatch", "reprint the label at the label station, never handwrite"),
    ("overtime approval", "obtain supervisor approval before extending the shift"),
    ("fire evacuation", "assemble at the muster point and report to the roll caller"),
    ("suspected theft", "secure the area and inform the site manager immediately"),
    ("cold room failure", "move stock to the backup cold room and log the outage"),
    ("pallet overflow", "move excess pallets to the overflow yard and update the system"),
    ("mismatched delivery", "hold the delivery in the discrepancy lane and audit it"),
    ("expired stock", "pull expired stock from pick faces and record the write-off"),
]
ACTIONS = [
    "notify the shift supervisor within 15 minutes",
    "complete form {form} and file it with the shift log",
    "photograph the area before any correction is made",
    "record the event in the system the same day",
    "escalate to the department head if unresolved after 2 hours",
    "place the affected goods in quarantine area Q{q}",
]


def make_doc(site, dept, idx, version, topic, form):
    phrase, core = topic
    q_area = random.randint(1, 4)
    body = f"""{dept.upper()} PROCEDURE - {site} SITE
Version: {version}
Effective Date: 20{random.randint(24, 26)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}

1. PURPOSE
This procedure defines how operators at the {site} site handle {phrase} during {dept.lower()} operations.

2. SCOPE
Applies to all {dept.lower()} staff on shifts A, B and C at {site}. Contractors follow the same steps unless stated otherwise.

3. CORE REQUIREMENT
3.1 The operator must {core}.
3.2 After the event, the operator must {random.choice(ACTIONS).format(form=form, q=q_area)}.

4. DETAILED STEPS
4.1 Identify the situation and stop the current task safely.
4.2 Apply the core requirement in section 3 without delay.
4.3 Complete the documentation described in section 5.

5. RECORDS
5.1 File form {form} with the shift log at the end of the shift. Form {form} is the only valid record for {phrase} at {site}.
5.2 The supervisor reviews records weekly and reports trends to the site manager.

6. RELATED DOCUMENTS
Refer to the master hygiene plan and the site emergency handbook for {site}.
"""
    return body


def main():
    shutil.rmtree(CORPUS_DIR, ignore_errors=True)
    os.makedirs(CORPUS_DIR, exist_ok=True)

    ground_truth = {}   # query -> (expected doc stem, unique form code)
    used_forms = set()
    n = 0
    for site in SITES:
        for dept in DEPTS:
            for idx in range(3):
                topic = TOPICS[(idx * 5 + DEPTS.index(dept)) % len(TOPICS)]
                version = random.choice(["1.0", "1.1", "2.0", "2.1", "2.3", "3.0"])
                stem = f"SOP-{site[:3].upper()}-{dept[:4].upper()}-{idx:02d}_v{version}"
                # unique form code per document
                while True:
                    form = "F%s-%s-%02d%s" % (
                        site[0].upper(), dept[:2].upper(), idx,
                        random.choice("ABCDEFGH"))
                    if form not in used_forms:
                        used_forms.add(form)
                        break
                body = make_doc(site, dept, idx, version, topic, form)
                with open(os.path.join(CORPUS_DIR, stem + ".txt"), "w") as f:
                    f.write(body)
                n += 1
                q = ("Which form must be filed for %s handling at the %s %s station?"
                     % (topic[0], site, dept))
                ground_truth[q] = (stem + ".txt", form)

    # add old-version duplicates for 30 docs (same family, lower version)
    dups = 0
    for name in sorted(os.listdir(CORPUS_DIR))[:30]:
        if "_v" not in name:
            continue
        oldname = name.replace("_v2", "_v1").replace("_v3", "_v1")
        if oldname == name:
            continue
        with open(os.path.join(CORPUS_DIR, name)) as f:
            body = f.read()
        body = body.replace("Version: ", "Version: 1.0\nXOLD: ", 1)
        # crude: just mark as older copy with same content
        with open(os.path.join(CORPUS_DIR, oldname), "w") as f:
            f.write(body)
        dups += 1

    total_files = len(os.listdir(CORPUS_DIR))

    data_dir = os.path.abspath(os.path.join(ROOT, "..", "stress_data"))
    shutil.rmtree(data_dir, ignore_errors=True)
    store = Store(data_dir)
    result = store.ingest_folder(CORPUS_DIR)
    print("Corpus files: %d | ingested docs: %d | chunks: %d" % (
        total_files, result["total_documents"], result["total_chunks"]))

    # ---- query battery: doc-level and fact-level ----
    doc_top1 = doc_top3 = fact_top1 = fact_top3 = 0
    total = 0
    failures = []
    for q, (expected, form) in ground_truth.items():
        hits = store.search(q, top_k=3)
        total += 1
        got = [h["doc_id"] for h in hits]
        texts = [h["text"] for h in hits]
        if got[:1] == [expected]:
            doc_top1 += 1
        if expected in got:
            doc_top3 += 1
        if texts and form in texts[0] + hits[0].get("context", ""):
            fact_top1 += 1
        if any(form in t + h.get("context", "") for t, h in zip(texts, hits)):
            fact_top3 += 1
        if expected not in got:
            failures.append((q, expected, got[:3]))

    print("\nQuery battery: %d queries" % total)
    print("Doc-level  top-1: %.1f%% | top-3: %.1f%%" % (
        100.0 * doc_top1 / total, 100.0 * doc_top3 / total))
    print("Fact-level top-1: %.1f%% | top-3: %.1f%%" % (
        100.0 * fact_top1 / total, 100.0 * fact_top3 / total))
    if failures:
        print("\nSample failures (up to 5):")
        for q, exp, got in failures[:5]:
            print("  Q: %s\n    expected %s, got %s" % (q, exp, got))

    conflicts = store.conflicts()
    print("\nVersion conflicts detected: %d families" % len(conflicts))

    t0 = time.time()
    for q in list(ground_truth)[:50]:
        store.search(q, top_k=5)
    dt = (time.time() - t0) / 50 * 1000
    print("Avg query latency: %.1f ms" % dt)


if __name__ == "__main__":
    main()
