# -*- coding: utf-8 -*-
"""模拟豆包：以 Streamable HTTP + Bearer Token 连接 MCP，握手并列出工具。"""
import asyncio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TOKEN = "CdDifyMcp_9f3a7c2e1b6048d5a2f9c8e7d6b5a432"
URL = "https://nickel-cdna-euro-timing.trycloudflare.com/mcp"


def _proxied_client(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(
        proxy="http://127.0.0.1:7890",
        trust_env=False,
        headers=headers,
        timeout=timeout,
        auth=auth,
    )


async def main():
    async with streamablehttp_client(
        URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        httpx_client_factory=_proxied_client,
    ) as (read, write, _):
        async with ClientSession(read, write) as s:
            r = await s.initialize()
            print("connected, server:", r.serverInfo.name, r.serverInfo.version)
            tools = await s.list_tools()
            print("tools count:", len(tools.tools))
            for t in tools.tools:
                print("  -", t.name)


asyncio.run(main())
