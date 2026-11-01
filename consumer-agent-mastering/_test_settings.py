# -*- coding: utf-8 -*-
"""联调测试：设置面板→运行时LLM配置→联网搜索全链路"""
import requests, json

BASE = "http://127.0.0.1:5000"

print("=" * 50)
print("[1] 页面加载测试（设置弹窗HTML是否渲染）")
r = requests.get(f"{BASE}/", timeout=10)
html = r.text
checks = ["settingsModal", "selProvider", "inpApiKey", "inpBaseUrl",
          "inpModel", "btnSaveSettings", "btnClearSettings", "btnSettings"]
for c in checks:
    print(f"  {'OK' if c in html else 'MISS'}  #{c}")
print(f"  页面状态码: {r.status_code}")

print()
print("[2] API测试：纯Mock模式（关闭联网+关闭大模型，应秒回）")
payload = {
    "query": "成都春熙路附近性价比高的火锅，预算100",
    "lat": 30.657, "lng": 104.066, "address": "成都春熙路",
    "llm_enabled": False,
    "web_search_enabled": False,
    "llm_config": {},
    "chat_history": [],
    "user_profile": {}
}
r = requests.post(f"{BASE}/api/agent/recommend", json=payload, timeout=30)
data = r.json()
print(f"  状态码: {r.status_code}  ok: {data.get('ok')}")
print(f"  meta.llm_enabled: {data.get('meta', {}).get('llm_enabled')}")
print(f"  meta.web_search_enabled: {data.get('meta', {}).get('web_search_enabled')}")
print(f"  meta.search_provider: {data.get('meta', {}).get('search_provider', '')[:80]}")
notes = data.get('meta', {}).get('search_notes', '')
print(f"  meta.search_notes: {notes[:120]}")
places = data.get('places', [])
print(f"  商家数: {len(places)}")
for p in places[:3]:
    print(f"    - {p.get('name', '?')} | 评分:{p.get('rating', '?')} | 人均:{p.get('avg_cost', '?')} | 源:{p.get('source', '?')}")
answer = data.get('answer', '')
print(f"  回复长度: {len(answer)} 字符")
print(f"  含思考链: {'OK' if '思考' in answer else 'MISS'}")

print()
print("[3] API测试：传入运行时llm_config（假Key，应快速失败走降级而非崩溃）")
payload2 = dict(payload)
payload2["llm_enabled"] = True
payload2["llm_config"] = {"provider": "deepseek", "api_key": "sk-fake-test-key-0001", "model": "deepseek-chat"}
r2 = requests.post(f"{BASE}/api/agent/recommend", json=payload2, timeout=90)
d2 = r2.json()
print(f"  状态码: {r2.status_code}  ok: {d2.get('ok')}")
a2 = d2.get('answer', '')
print(f"  回复长度: {len(a2)} 字符")
print(f"  含思考链: {'OK' if '思考' in a2 else 'MISS'}")
print(f"  meta: {json.dumps({k: d2.get('meta', {}).get(k) for k in ['llm_enabled', 'fallback', 'search_provider']}, ensure_ascii=False)[:150]}")

print()
print("全链路测试完成")