# -*- coding: utf-8 -*-
"""MCP 客户端自测：连接本地 dify-mcp-server，列工具 + 调用 list_apps，结果写入文件。"""
import asyncio
import os
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()
URL = "http://127.0.0.1:9000/mcp"
TOKEN = os.getenv("MCP_HTTP_TOKEN", "")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_result.txt")

lines = []


def p(s=""):
    print(s)
    lines.append(str(s))


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with streamablehttp_client(URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()

            tools = await s.list_tools()
            p("== 已加载的 MCP 工具 ==")
            for t in tools.tools:
                p("  - " + t.name)

            p("")
            p("== 调用 list_apps（真实登录 Dify）==")
            r = await s.call_tool("list_apps", {})
            for c in r.content:
                if hasattr(c, "text"):
                    p(c.text)
            p("isError = " + str(r.isError))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("written:", OUT)


asyncio.run(main())
