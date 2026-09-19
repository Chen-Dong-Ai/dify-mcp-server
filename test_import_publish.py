# -*- coding: utf-8 -*-
"""验证 import_dsl 与 publish_app：导入为临时新应用 → 发布 → 测试（不影响主应用）。"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from server import DIFY_BASE_URL, DIFY_EMAIL, DIFY_PASSWORD, DifyClient  # noqa: E402

dsl_text = open(os.path.join(HERE, "backup-智能锁客服-原始.yml"), encoding="utf-8").read()

c = DifyClient(DIFY_BASE_URL, DIFY_EMAIL, DIFY_PASSWORD)
c.login()

NAME = "MCP导入演示-可删"
res = c.import_app(dsl_text, NAME)
print("== import 返回：")
for k, v in res.items():
    print("   ", k, "=", v)
new_id = res.get("app_id")
print(">> 新应用 id：", new_id)

pub = c.publish(new_id)
print("== publish 返回：", pub)

ans = c.debug_chat(new_id, "怎么开发票")
print("== 新应用测试（末尾200字）：\n", ans[-200:])
