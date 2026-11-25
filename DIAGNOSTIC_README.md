# SOP Diagnostic Package

Run a health-check on your own SOP document library — locally.
**Your documents never leave your machine.** The generated report contains
no document text: only filenames, versions, statistics and recommendations,
so it is safe to share back with us for a solution proposal.

## What it checks

- **Version conflicts** — multiple versions of the same procedure loaded at once
- **Missing metadata** — documents without a version number or effective date
- **Stale documents** — effective date older than a configurable threshold (default 18 months)
- **Coverage gaps** — common warehouse topics (receiving, putaway, picking, packing, dispatch, returns, damage, cold chain, stock counts, safety) that your library cannot answer
- **Retrieval self-test** — sample questions with the engine's top hits and scores

## Quick start (3 steps)

Requires Python 3.10+.

1. **Install dependencies** (only needed for PDF/DOCX support):

   ```bash
   pip install -r requirements.txt
   ```

2. **Point it at your SOP folder** (`.pdf`, `.docx`, `.txt`, `.md`, `.csv`, `.json`, `.log`):

   ```bash
   python tools/diagnose_cli.py /path/to/your/sop/folder
   ```

3. **Open the report** — written to `data/diagnosis_report.md`
   (and `data/diagnosis_report.json` for machine reading).

## Options

```bash
python tools/diagnose_cli.py <folder> \
    --data-dir ./my-diag-data \      # where the local index is stored
    --report-dir ./my-reports \      # where reports are written
    --stale-months 12                # staleness threshold
```

## Sharing the report

Send `diagnosis_report.md` (or the `.json` file) back to us — we will turn
it into a phased improvement proposal: pilot in one site first, then scale.
