# -*- coding: utf-8 -*-
"""联调验证：开关切换 + DDG联网 + 降级链"""
import requests

BASE = "http://127.0.0.1:5000/api/agent/recommend"

def test(label, **overrides):
    payload = {
        "query": "附近性价比高的川菜，预算100",
        "address": "成都市武侯区",
        "chat_history": [],
        "user_profile": {"people": 2, "transport": "步行/骑行"},
        "llm_enabled": True,
        "web_search_enabled": True,
    }
    payload.update(overrides)
    r = requests.post(BASE, json=payload, timeout=60)
    d = r.json()
    meta = d.get("meta", {})
    print(f"[{label}]")
    print(f"  llm_enabled={meta.get('llm_enabled')} web={meta.get('web_search_enabled')}")
    print(f"  provider={meta.get('search_provider')}")
    print(f"  llm_label={meta.get('llm')}")
    print(f"  errors={meta.get('search_errors')}")
    print(f"  places={len(d.get('places', []))} cot={all(k in d.get('answer','') for k in ['### 🤔','### 🏆','### 💰'])}")
    for p in d.get("places", [])[:3]:
        print(f"    - {p['name']} | {p.get('cost_text','')} | {p.get('source','')}")
    print()
    return d

# 1. 默认全开：联网搜索（DDG→OSM→Mock）
test("全开（联网+AI）")

# 2. 关闭联网搜索：纯Mock秒回
test("关闭联网", web_search_enabled=False)

# 3. 关闭AI思考：规则兜底快速模式
test("关闭AI思考", llm_enabled=False)

# 4. 全关：最快路径
test("全关（最快）", llm_enabled=False, web_search_enabled=False)