# SOP Retrieval — Self-Serve Test Package

Evaluate SOP retrieval on your own data, locally. Your documents never
leave your machine.

## What is inside

- `run_server.py` — starts the MCP server (stdio transport)
- `tools/ingest_cli.py` — one-command ingestion of your SOP folder
- `sample_sops/` — six sample warehouse SOPs to try immediately
- `sop_mcp/` — server code (PDF/DOCX/text ingestion, pure-Python retrieval)
- `SCOPE.md` — what this package does and does not do (read first)

## Requirements

- Python 3.10+
- `pip install -r requirements.txt` (installs the `mcp` package only)

## Quick start (3 steps)

1. **Ingest your documents**

   ```bash
   python tools/ingest_cli.py /path/to/your/sop/folder
   ```

   Supported file types: `.pdf`, `.docx`, `.txt`, `.md`, `.csv`, `.json`, `.log`.
   Re-running is safe — unchanged files are skipped.

2. **Start the MCP server**

   ```bash
   python run_server.py
   ```

3. **Connect from any MCP client** (Claude Desktop, Cursor, etc.) with
   this configuration:

   ```json
   {
     "mcpServers": {
       "sop-retrieval": {
         "command": "python",
         "args": ["/full/path/to/this/folder/run_server.py"]
       }
     }
   }
   ```

Then ask questions like:

- "What must be checked before dispatching goods?"
- "What do I do if the vehicle seal number does not match?"
- "Where do damaged cartons go during putaway?"

Every answer comes back with its **source**: document name, version,
and section — so an operator can verify before acting.

## Tools provided by the server

| Tool | What it does |
|---|---|
| `ingest_documents(folder_path)` | Load SOP files into the index |
| `search_procedure(query, top_k)` | Retrieve the right procedure passage with source |
| `list_documents()` | Show loaded documents and detected versions |
| `check_versions()` | Flag multiple versions of the same procedure |
| `trial_status()` | Show evaluation period status |

## Version handling

If two versions of the same procedure are loaded (e.g.
`SOP-WH-003_Picking_v3.0.txt` and `SOP-WH-003_Picking_v3.1.txt`),
`search_procedure` prefers the highest version and flags the conflict
via `check_versions()`.

## Evaluation period

Free for 30 days from first run, unlimited documents. For the managed
production version (integration with your ERP/AI systems, hosted
indexing, multi-site support), contact us.

## Scope

Read `SCOPE.md` before evaluating: it lists exactly what this package
does, what it does not do, and what is out of scope. Nothing beyond
that scope is promised.

## Troubleshooting

- **"unsupported type" when ingesting** — the file extension is not in
  the supported list. Convert it to PDF, DOCX or plain text.
- **PDF ingests but content looks wrong** — the PDF may be a scan
  without a text layer. SCOPE.md covers this limit; use text-based
  PDFs or DOCX.
- **Answers cite an old version** — run `check_versions()`; if several
  versions of one procedure are loaded, remove the outdated files and
  re-ingest.
- **MCP client cannot connect** — make sure the `args` path in your
  client config is the absolute path to `run_server.py`, and that
  `python` resolves to Python 3.10+.

## More from us

This package is one piece of a broader verifiable-agent toolkit. The official
site — with the full works catalog and background — lives at
[huodouai.com](https://www.huodouai.com/works/sop-mcp-test-v0.1.html).

## License

MIT — see [LICENSE](LICENSE). The evaluation-period terms in SCOPE.md apply on
top of it for the trial gate; the managed production version is licensed
separately.
