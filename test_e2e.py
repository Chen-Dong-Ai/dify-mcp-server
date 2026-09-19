# -*- coding: utf-8 -*-
"""端到端验证正式 update_workflow：模拟 Agent 标准流程 export→改→update→test。"""
import os, sys, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from server import DIFY_BASE_URL, DIFY_EMAIL, DIFY_PASSWORD, DifyClient  # noqa: E402

TARGET_NODE = "1789656946791"  # 知识库回答员 LLM
SUFFIX_RULE = (
    "5. 每次回答的最后，另起一行，固定附上一句话："
    "——本回答由「陈冬 AI 演示客服」自动生成（MCP 编排演示）。"
)

# 1) 模拟 export_dsl 拿到的干净样板（原始备份，知识库 id 为混淆串、检索为 rerank）
dsl = yaml.safe_load(open(os.path.join(HERE, "backup-智能锁客服-原始.yml"), encoding="utf-8"))

# 2) 模拟 Agent 的增量改动：给知识库回答员 system prompt 加固定后缀
for n in dsl["workflow"]["graph"]["nodes"]:
    d = n.get("data", {})
    if n.get("id") == TARGET_NODE:
        for msg in d["prompt_template"]:
            if msg["role"] == "system" and "MCP 编排演示" not in msg["text"]:
                msg["text"] = msg["text"].rstrip() + "\n" + SUFFIX_RULE
new_yaml = yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False)

c = DifyClient(DIFY_BASE_URL, DIFY_EMAIL, DIFY_PASSWORD)
c.login()
app = c.find_app("智能锁客服 Demo")

# 3) 正式工具回写（内部自动还原知识库引用 + 归一化检索 + 乐观锁）
res = c.update_workflow(app["id"], new_yaml)
print("== update_workflow 返回：")
for x in res["notes"]:
    print("   ·", x)
print("   result:", res["result"], " hash:", res["hash"])

# 4) run_test 验证
for q in ["怎么开发票", "指纹怎么录"]:
    print("=" * 25, "问题：", q)
    ans = c.debug_chat(app["id"], q)
    print(ans[-350:])
    print(">> 命中知识库且含固定后缀：", ("MCP 编排演示" in ans))
