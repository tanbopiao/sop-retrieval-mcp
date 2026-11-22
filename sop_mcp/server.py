"""MCP server exposing SOP retrieval tools (stdio transport)."""
import os
import sys

from mcp.server.fastmcp import FastMCP

from .store import Store
from . import trial

DATA_DIR = os.environ.get(
    "SOP_MCP_DATA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)

mcp = FastMCP("sop-retrieval")
store = Store(DATA_DIR)


@mcp.tool()
def ingest_documents(folder_path: str) -> dict:
    """Load SOP documents (txt/md/csv/json/log) from a folder into the
    retrieval index. Re-ingesting unchanged files is a no-op."""
    lic = trial.check_trial(DATA_DIR)
    if not lic["ok"]:
        return {"error": lic["message"]}
    result = store.ingest_folder(folder_path)
    result["trial"] = lic["message"]
    return result


@mcp.tool()
def search_procedure(query: str, top_k: int = 5) -> dict:
    """Search loaded SOPs for an answer to an operational question.
    Returns matching passages with full source attribution: document,
    version, section and excerpt. Latest document version is preferred
    when several versions of the same procedure are loaded."""
    hits = store.search(query, top_k=max(1, min(top_k, 20)))
    return {
        "query": query,
        "results": [
            {
                "answer_excerpt": h["text"],
                "related_passages": h.get("context", ""),
                "source": {
                    "document": h["doc_id"],
                    "version": h["version"],
                    "section": h["section"],
                    "part": h["part"],
                },
                "relevance": h["score"],
            }
            for h in hits
        ],
        "note": "Verify the version above is the one your operators should follow.",
    }


@mcp.tool()
def list_documents() -> dict:
    """List all loaded SOP documents with their detected versions."""
    return {"documents": store.list_documents()}


@mcp.tool()
def check_versions() -> dict:
    """Detect version conflicts: multiple versions of the same procedure
    loaded at once, which can cause operators to follow outdated steps."""
    return {"conflicts": store.conflicts()}


@mcp.tool()
def trial_status() -> dict:
    """Show evaluation period status."""
    return trial.check_trial(DATA_DIR)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
