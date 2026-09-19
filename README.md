# dify-mcp-server

> 用自然语言驱动 Dify 编排工作流：把 Dify 的工作流管理能力封装成 **MCP（Model Context Protocol）工具**，
> 大模型 Agent（豆包工作台 / Codex / Cherry Studio 等）加载后，用户只需说一句话，
> Agent 即可自动完成 **导出 DSL → 增量改编 → 导入 Dify → 发消息测试 → 发布上线** 的全流程。

## 这是什么

低代码平台（Dify）让应用搭建变快了，但「在画布上拖节点、连线、配参数」仍是重复手工劳动。
本项目把这些操作变成 Agent 可调用的标准工具：

```
用户：「给客服工作流的售后分支加一个订单号提取节点，没提取到就提示用户提供」
   │
   ▼
大模型 Agent（豆包工作台）
   │  ① export_dsl   导出当前工作流 DSL 作为样板
   │  ② 在 DSL 上增量修改（新增参数提取器节点 + 连线）
   │  ③ update_workflow 回写草稿
   │  ④ run_test     发测试消息验证
   │  ⑤ publish_app  人确认后发布
   ▼
Dify（Cloud / 自建）  ──工作流更新并上线
```

**人的职责**：提业务需求、审查 Agent 的变更、验收测试结果；**Agent 的职责**：执行编排。
工作流以 DSL（YAML）为载体，可 Git 版本化、可 diff 审查，变更可追溯。

## 工具清单（6 个 MCP 工具）

| 工具 | 作用 | 对应 Dify 能力 |
|---|---|---|
| `list_apps` | 列出工作空间全部应用 | 应用列表 |
| `export_dsl` | 导出某应用的完整 DSL（YAML） | 导出 DSL |
| `import_dsl` | 用 DSL 从零创建新 Chatflow | 导入 DSL |
| `update_workflow` | 用新 DSL 覆盖更新编排（草稿态） | 工作流导入 |
| `publish_app` | 发布最新编排 | 发布 |
| `run_test` | 发消息端到端测试并返回回答 | 调试运行 |

> 此外内置 Console 登录态自动续期（账号登录、token 过期自动刷新），属内部鉴权机制，不单独暴露为 MCP 工具。

支持两种传输：**stdio**（本地调试）与 **Streamable HTTP**（远程接入，带 Bearer Token 鉴权）。

## Agent 使用范式（重要）

修改已有工作流时，Agent 被要求严格遵循：

1. 先 `export_dsl` 拿当前 DSL 作为样板（禁止凭记忆臆造节点 id / 连线）；
2. 在样板上做**最小增量修改**；
3. `update_workflow` 回写草稿；
4. `run_test` 同时验证「应命中」与「应兜底」话术；
5. **人确认后**才 `publish_app`（Human-in-the-Loop，不允许 Agent 自行发布）。

## 快速开始

### 1. 安装

需要 Python 3.10+。

```bash
pip install -r requirements.txt
# 国内网络如安装慢，使用清华镜像：
# pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置凭证

```bash
cp .env.example .env
# 编辑 .env，填入 Dify 登录邮箱、密码；
# DIFY_BASE_URL：Dify Cloud 填 https://udify.app ，自建版填你的域名
```

> `.env` 含账号密码，已在 `.gitignore` 中排除，切勿提交仓库。

### 3. 本地验证（HTTP 模式，最快）

```bash
# Windows PowerShell：
$env:MCP_TRANSPORT="http"; $env:HTTP_PORT="9000"; python server.py
```

服务启动在 `http://127.0.0.1:9000/mcp`，在支持 MCP 的客户端中添加该地址即可调试。

stdio 模式直接 `python server.py`（由 MCP 客户端以子进程方式拉起）。

## 接入豆包工作台

1. 将服务以 HTTP 模式部署到一台公网可访问的服务器（见下节）；
2. 在豆包电脑版中找到 **MCP / 连接器 / 自定义工具** 入口（不同版本菜单名略有差异）；
3. 新建连接器，类型选 **HTTP / Streamable HTTP（或 SSE）**：
   - URL：`http://你的服务器地址:9000/mcp`
   - Header：`Authorization: Bearer 你在 .env 里设置的 MCP_HTTP_TOKEN`
4. 连接成功后，工具列表出现 `list_apps` 等 6 个工具即接入完成；
5. 对话框直接用自然语言下达编排指令。

> 具体菜单以豆包客户端实际界面为准。

## 部署到服务器（Docker，推荐）

```bash
# 在服务器上准备好含真实配置的 .env，然后：
docker build -t dify-mcp-server .
docker run -d --name dify-mcp \
  --restart unless-stopped \
  --env-file .env \
  -p 9000:9000 \
  dify-mcp-server
```

- 云服务器安全组放行 9000 端口；
- 生产建议挂 HTTPS（Nginx 反代 + 证书）后再给豆包接入；
- 内存占用约 100MB 级，2核4G 小服务器足够。

## 安全说明

- Dify 账号密码只存在部署机的 `.env` 中，不硬编码、不进仓库；
- HTTP 模式必须设置 `MCP_HTTP_TOKEN`，连接器与服务端双方校验；
- Agent 只有在人确认后才执行发布，避免未审查变更上线；
- 建议 Dify 账号开启独立密码、按需使用，不与主账号混用。

## 已知边界（如实说明）

- Dify 的「应用编排 / 导入 / 发布」走的是 Console API（网页端同款接口），**不是官方公开 API**，
  不同 Dify 版本路径可能有差异；本项目已对导入接口做新旧路径兼容，若遇版本差异，按实际响应微调即可；
- 公开 App API 只能「使用」应用（对话、传知识库），「搭建/改编排」必须走 Console API，这是本项目选择它的原因；
- 知识库 embedding、模型供应商等依赖在 Dify 侧配置，本服务不重复实现。

## 技术栈

Python · MCP Python SDK（FastMCP）· httpx · Streamable HTTP / stdio · Docker
