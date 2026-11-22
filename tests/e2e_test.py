#!/usr/bin/env python3
"""End-to-end test: launch the MCP server over stdio and exercise every
tool through the real MCP protocol."""
import asyncio
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DATA_DIR = os.path.abspath(os.path.join(ROOT, "..", "e2e_data"))
SAMPLES = os.path.join(ROOT, "sample_sops")


async def main():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    env = dict(os.environ)
    env["SOP_MCP_DATA"] = DATA_DIR
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(ROOT, "run_server.py")],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. ingest sample SOPs
            r = await session.call_tool("ingest_documents",
                                        {"folder_path": SAMPLES})
            data = r.content[0].text
            print("ingest_documents ->", data[:200].replace("\n", " "))
            assert '"total_documents": 6' in data, data

            # 2. search with source attribution
            r = await session.call_tool(
                "search_procedure",
                {"query": "what must be checked before dispatching goods?",
                 "top_k": 3})
            data = r.content[0].text
            print("search_procedure ->", data[:220].replace("\n", " "))
            assert "SOP-WH-005" in data and "version" in data

            # 3. list documents
            r = await session.call_tool("list_documents", {})
            data = r.content[0].text
            assert "SOP-WH-001" in data
            print("list_documents -> 6 documents listed")

            # 4. version conflicts (clean corpus -> none expected)
            r = await session.call_tool("check_versions", {})
            data = r.content[0].text
            print("check_versions ->", data[:120].replace("\n", " "))

            # 5. trial status
            r = await session.call_tool("trial_status", {})
            data = r.content[0].text
            print("trial_status ->", data[:140].replace("\n", " "))
            assert "days_left" in data

    print("\nE2E: ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
