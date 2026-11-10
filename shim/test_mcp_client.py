"""Self-test: connect to the local MCP server and call the tool (runs on 102 in the venv)."""
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    async with streamablehttp_client("http://127.0.0.1:8901/mcp") as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            res = await s.call_tool("search_lumerical_docs", {"query": "how to set mesh accuracy in FDTD", "top_k": 2})
            txt = ""
            for c in res.content:
                txt += getattr(c, "text", str(c))
            print("RESULT:\n" + txt[:700])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # noqa: BLE001
        print("SELFTEST_ERR", type(e).__name__, e)
        sys.exit(1)
