# -*- coding: utf-8 -*-
"""验证 export_dsl 与 run_test，结果写入文件。"""
import asyncio
import os
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()
URL = "http://127.0.0.1:9000/mcp"
TOKEN = os.getenv("MCP_HTTP_TOKEN", "")
APP = "智能锁客服 Demo"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_tools.txt")
L = []


def p(s=""):
    L.append(str(s))
    print(s)


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with streamablehttp_client(URL, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            p("== export_dsl（导出完整 DSL）==")
            res = await s.call_tool("export_dsl", {"app_id_or_name": APP})
            dsl = res.content[0].text
            p("DSL 总长度：%d 字符" % len(dsl))
            p("---- 前 1200 字 ----")
            p(dsl[:1200])

            p("")
            p("== run_test：指纹怎么录（端到端跑工作流）==")
            rt = await s.call_tool(
                "run_test",
                {"app_id_or_name": APP, "message": "指纹怎么录"},
            )
            p(rt.content[0].text)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


asyncio.run(main())
