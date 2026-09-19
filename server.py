# -*- coding: utf-8 -*-
"""
dify-mcp-server
================
通过 MCP 协议，让大模型 Agent（豆包工作台 / Codex / Cherry Studio 等）
用自然语言驱动 Dify 完成工作流的「导出 → 改编 → 导入 → 测试 → 发布」。

传输模式（由环境变量 MCP_TRANSPORT 决定）：
  stdio : 本地调试，Agent 以子进程方式启动本程序（默认）
  http  : Streamable HTTP，部署到服务器后供豆包工作台远程接入

说明：Dify「编排应用」的接口（导入 DSL / 发布）属于 Console API（网页端同款），
本服务用账号邮箱登录换取 token，并在过期时自动刷新；凭证只从 .env 读取，不写死、不入库。
"""

import os
import json
import time
import base64

import httpx
import yaml
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "https://cloud.dify.ai").rstrip("/")
DIFY_EMAIL = os.getenv("DIFY_EMAIL", "")
DIFY_PASSWORD = os.getenv("DIFY_PASSWORD", "")
# Google / GitHub 等第三方登录账号没有密码，改用从浏览器抓取的令牌（见 README）
DIFY_ACCESS_TOKEN = os.getenv("DIFY_ACCESS_TOKEN", "")
DIFY_REFRESH_TOKEN = os.getenv("DIFY_REFRESH_TOKEN", "")
TOKEN_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token.json")
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "9000"))
HTTP_TOKEN = os.getenv("MCP_HTTP_TOKEN", "")
TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")

mcp = FastMCP("dify-mcp-server")


# ============================ Dify Console 客户端 ============================

class DifyClient:
    """封装 Dify Console API：登录鉴权 + 应用/工作流管理。"""

    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.csrf_token: str | None = None
        # httpx.Client 自动保存并回传登录后下发的 cookie（access_token / refresh_token）
        self.http = httpx.Client(
            timeout=httpx.Timeout(60.0, read=120.0),
            follow_redirects=True,
        )

    # ---------- 鉴权 ----------

    def login(self) -> None:
        # Dify 前端登录时会把密码做 Base64 编码后传输，这里保持一致
        encoded_password = base64.b64encode(self.password.encode("utf-8")).decode("utf-8")
        r = self.http.post(
            f"{self.base_url}/console/api/login",
            json={
                "email": self.email,
                "password": encoded_password,
                "language": "zh-Hans",
                "remember_me": True,
            },
        )
        r.raise_for_status()
        # 新版 Dify 登录成功后，token 通过 HttpOnly Cookie 下发（响应体 data 为 null）
        self.csrf_token = self.http.cookies.get("csrf_token")
        if not self.csrf_token:
            raise RuntimeError("登录后未获取到 csrf_token，请检查账号密码。")

    def _headers(self) -> dict:
        # access_token 的 cookie 由 httpx 自动回传；受保护接口还需带 CSRF 头
        return {
            "X-CSRF-Token": self.csrf_token or "",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, retry: int = 1, **kwargs) -> httpx.Response:
        """带自动登录的请求封装；cookie 过期（401）时重新登录后重试。"""
        if not self.csrf_token:
            self.login()
        r = self.http.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        if r.status_code == 401 and retry > 0:
            self.login()
            r = self.request(method, path, retry=retry - 1, **kwargs)
        return r

    # ---------- 应用管理 ----------

    def list_apps(self) -> list:
        r = self.request("GET", "/console/api/apps?page=1&page_size=100")
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data

    def find_app(self, key: str) -> dict | None:
        """按 id 精确、名称精确、名称包含的优先级找应用。"""
        apps = self.list_apps()
        for a in apps:
            if a.get("id") == key or a.get("name") == key:
                return a
        for a in apps:
            if key and key in (a.get("name") or ""):
                return a
        return None

    def export_dsl(self, app_id: str) -> str:
        r = self.request("GET", f"/console/api/apps/{app_id}/export")
        r.raise_for_status()
        data = r.json().get("data", r.json())
        # export 接口一般直接返回 YAML 字符串；若返回 dict 则序列化
        if isinstance(data, str):
            return data
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

    def import_app(self, yaml_content: str, name: str) -> dict:
        """导入 DSL 创建新应用。
        1.x 语义：依赖齐全直接 200 完成；缺插件依赖时返回 202 PENDING，需 /confirm 确认。"""
        body = {
            "mode": "yaml-content",
            "yaml_content": yaml_content,
            "name": name,
            "icon_type": "emoji",
            "icon": "🤖",
            "icon_background": "#E0F2FE",
        }
        r = self.request("POST", "/console/api/apps/imports", json=body)
        data = r.json()
        if r.status_code == 202 or data.get("status") == "pending":
            confirm = self.request("POST", f"/console/api/apps/imports/{data.get('id')}/confirm")
            confirm.raise_for_status()
            return confirm.json()
        r.raise_for_status()
        return data

    def list_datasets(self) -> list:
        r = self.request("GET", "/console/api/datasets?page=1&page_size=100")
        r.raise_for_status()
        data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data

    @staticmethod
    def _is_uuid(value) -> bool:
        return isinstance(value, str) and len(value) == 36 and value.count("-") == 4

    def update_workflow(self, app_id: str, yaml_content: str) -> dict:
        """把 Agent 改好的 DSL 回写为「草稿」（不触碰线上已发布版本）。

        导出 DSL 会对知识库 id 做 Base64 混淆，而 /workflows/draft 不执行导入时的
        资源解密，因此这里：①把知识库引用还原为当前工作空间真实 UUID；
        ②把检索配置归一化为权重混合（向量+关键词，不依赖额外 rerank 插件）；
        ③带当前草稿 hash 走乐观锁回写。返回 {result, hash, notes}。
        """
        dsl = yaml.safe_load(yaml_content)
        wf = dsl["workflow"]
        graph = wf["graph"]
        notes: list[str] = []

        datasets = self.list_datasets()
        real_ids = [d.get("id") for d in datasets]

        for n in graph.get("nodes", []):
            d = n.get("data", {})
            if d.get("type") != "knowledge-retrieval":
                continue

            # ① 还原混淆的知识库引用
            ids = d.get("dataset_ids") or []
            unresolved = [x for x in ids if not self._is_uuid(x)]
            if unresolved:
                if len(real_ids) == len(unresolved):
                    mapped = real_ids[: len(unresolved)]
                elif len(real_ids) == 1:
                    mapped = [real_ids[0]] * len(unresolved)
                else:
                    raise RuntimeError(
                        f"知识库引用 {unresolved} 无法自动对应；请在 DSL 中直接填写真实知识库 id：{real_ids}"
                    )
                new_ids, mi = list(ids), 0
                for i, x in enumerate(new_ids):
                    if not self._is_uuid(x):
                        new_ids[i] = mapped[mi]
                        mi += 1
                d["dataset_ids"] = new_ids
                notes.append(f"已还原知识检索节点「{d.get('title')}」的知识库引用为真实 UUID")

            # ② 检索配置归一化到权重混合
            rc = d.get("multiple_retrieval_config")
            if rc and (rc.get("reranking_enable") or rc.get("reranking_mode") != "weighted_score"):
                rc["reranking_enable"] = False
                rc["reranking_mode"] = "weighted_score"
                rc["reranking_model"] = None
                rc["score_threshold"] = None
                notes.append(f"知识检索节点「{d.get('title')}」已归一化为权重混合检索（向量0.7/关键词0.3）")

        # ③ 取当前草稿 hash（乐观锁），再回写
        gd = self.request("GET", f"/console/api/apps/{app_id}/workflows/draft").json()
        body = {
            "graph": graph,
            "features": wf.get("features", {}),
            "conversation_variables": wf.get("conversation_variables", []),
            "hash": gd.get("unique_hash") or gd.get("hash"),
        }
        r = self.request("POST", f"/console/api/apps/{app_id}/workflows/draft", json=body)
        if r.status_code == 409:  # hash 过期，重新取后重试一次
            gd = self.request("GET", f"/console/api/apps/{app_id}/workflows/draft").json()
            body["hash"] = gd.get("unique_hash") or gd.get("hash")
            r = self.request("POST", f"/console/api/apps/{app_id}/workflows/draft", json=body)
        r.raise_for_status()
        out = r.json()
        return {"result": out.get("result"), "hash": out.get("hash"), "notes": notes}

    def publish(self, app_id: str) -> dict:
        r = self.request("POST", f"/console/api/apps/{app_id}/workflows/publish")
        r.raise_for_status()
        return r.json()

    def debug_chat(self, app_id: str, query: str, timeout: int = 90) -> str:
        """走 advanced-chat 草稿调试接口（SSE 流），拼出最终回答，用于端到端测试。"""
        answer: list[str] = []
        started = time.time()
        with self.http.stream(
            "POST",
            f"{self.base_url}/console/api/apps/{app_id}/advanced-chat/workflows/draft/run",
            headers={**self._headers(), "Accept": "text/event-stream"},
            json={
                "inputs": {},
                "query": query,
                "files": None,
                "conversation_id": None,
                "parent_message_id": None,
            },
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if evt.get("event") in ("message", "agent_message"):
                    answer.append(evt.get("answer", ""))
                elif evt.get("event") == "message_end":
                    break
                elif evt.get("event") == "error":
                    answer.append(f"[工作流报错] {evt.get('message', '')}")
                    break
                if time.time() - started > timeout:
                    answer.append("\n[测试超时截断]")
                    break
        return "".join(answer) or "[未返回内容]"


def get_client() -> DifyClient:
    if not DIFY_EMAIL or not DIFY_PASSWORD:
        raise RuntimeError("未配置 DIFY_EMAIL / DIFY_PASSWORD，请先复制 .env.example 为 .env 并填写。")
    c = DifyClient(DIFY_BASE_URL, DIFY_EMAIL, DIFY_PASSWORD)
    c.login()
    return c


def _resolve_app(c: DifyClient, key: str) -> dict | str:
    app = c.find_app(key)
    return app if app else f"未找到应用：{key}（可先调 list_apps 确认名称/id）"


# ============================ MCP 工具（给 Agent 调用） ============================

@mcp.tool()
def list_apps() -> str:
    """列出 Dify 工作空间中的全部应用（id、名称、模式、更新时间）。
    搭建或修改工作流前，先用本工具确认目标应用是否存在。"""
    c = get_client()
    apps = c.list_apps()
    rows = [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "mode": a.get("mode"),
            "updated_at": a.get("updated_at"),
        }
        for a in apps
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2)


@mcp.tool()
def export_dsl(app_id_or_name: str) -> str:
    """导出指定应用的完整工作流 DSL（YAML 文本）。
    【重要】修改任何已有工作流前，必须先调用本工具拿到当前 DSL，以它为样板做增量修改，
    禁止凭记忆从零臆造 DSL（节点 id、连线、模型配置必须与样板一致）。"""
    c = get_client()
    app = _resolve_app(c, app_id_or_name)
    if isinstance(app, str):
        return app
    return c.export_dsl(app["id"])


@mcp.tool()
def import_dsl(yaml_content: str, app_name: str = "Agent生成应用") -> str:
    """用一段完整 DSL 在 Dify 中创建一个全新的 Chatflow 应用（从零搭建时使用）。
    注意：创建后处于未发布状态，需要再调用 publish_app 才会对外生效。
    返回新应用的 id。"""
    c = get_client()
    res = c.import_app(yaml_content, app_name)
    return "创建成功：\n" + json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def update_workflow(app_id_or_name: str, yaml_content: str) -> str:
    """用新 DSL 覆盖更新指定应用的工作流编排（草稿态，不影响线上已发布版本）。
    标准用法：export_dsl 导出 → 在 YAML 上做增量修改 → 本该工具回写 → run_test 验证 → publish_app。
    工具会自动还原 DSL 中混淆的知识库引用、把检索配置归一化为权重混合，无需手工处理。"""
    c = get_client()
    app = _resolve_app(c, app_id_or_name)
    if isinstance(app, str):
        return app
    res = c.update_workflow(app["id"], yaml_content)
    lines = ["编排已更新（草稿态，尚未发布）。"]
    lines.extend("· " + n for n in res.get("notes", []))
    lines.append("新草稿 hash：" + str(res.get("hash")))
    lines.append("请接着用 run_test 验证效果，再决定是否 publish_app。")
    return "\n".join(lines)


@mcp.tool()
def publish_app(app_id_or_name: str) -> str:
    """发布指定应用的最新工作流编排，发布后 WebApp 与 API 才会使用新版本。"""
    c = get_client()
    app = _resolve_app(c, app_id_or_name)
    if isinstance(app, str):
        return app
    res = c.publish(app["id"])
    return "已发布：\n" + json.dumps(res, ensure_ascii=False, indent=2)


@mcp.tool()
def run_test(app_id_or_name: str, message: str) -> str:
    """向指定应用发送一条测试消息，返回最终回答（走 Dify 调试通道，会真实执行整个工作流）。
    用于每次改完编排后的端到端验证。建议同时验证「应命中」和「应兜底」两类话术。"""
    c = get_client()
    app = _resolve_app(c, app_id_or_name)
    if isinstance(app, str):
        return app
    return c.debug_chat(app["id"], message)


# ============================ 启动入口 ============================

def build_http_app():
    """Streamable HTTP 模式：给 /mcp 路径加 Bearer Token 鉴权。"""
    import uvicorn
    from starlette.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    app = mcp.streamable_http_app()

    if HTTP_TOKEN:
        class TokenAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.url.path.startswith("/mcp"):
                    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                    if token != HTTP_TOKEN:
                        return JSONResponse({"error": "unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(TokenAuthMiddleware)

    return app, uvicorn


if __name__ == "__main__":
    if TRANSPORT == "http":
        app, uvicorn = build_http_app()
        uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run()
