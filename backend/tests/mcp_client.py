"""Talk to the ChronoMem MCP server over stdio exactly like Claude Desktop/Cursor would.
Run: uv run python tests/mcp_client.py
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "chronomem.mcp_server"],
    env={"CHRONOMEM_USER": "mcp_test"},
)


async def main():
    from chronomem.db import delete_user
    delete_user("mcp_test")
    async with stdio_client(PARAMS) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("tools:", [t.name for t in tools.tools])

            async def call(name, **args):
                res = await s.call_tool(name, args)
                out = json.loads(res.content[0].text)
                print(f"\n{name}({args}) ->", json.dumps(out)[:300])
                return out

            await call("begin_session")
            await call("remember", subject="user", predicate="city", object="Pune", kind="identity", source="I live in Pune")
            c = await call("remember", subject="user", predicate="city", object="Delhi", kind="identity", source="I'm in Delhi now")
            assert c["status"] == "contradiction"
            await call("resolve", fact_id=c["fact_id"], keep="new")
            h = await call("why_changed", topic="city")
            assert [v["object"] for v in h["timelines"][0]["versions"]] == ["Pune", "Delhi"]
            await call("recall", query="city")
            print("\nMCP OK")


asyncio.run(main())
