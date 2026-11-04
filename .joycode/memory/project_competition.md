---
name: 大赛项目背景与可靠性原则
description: consumer-agent-mastering 项目面向全国AI应用创新大赛，Demo 永不白屏是最高优先级，多级降级链路是有意设计
type: project
---

本项目（consumer-agent-mastering）是面向《全国人工智能应用创新大赛》的"AI出行与消费性价比决策 Agent"演示项目，Flask + 原生前端 + DeepSeek/Ollama + DDG/高德搜索。

**Why:** 比赛现场演示，任何 500 白屏或空结果都会直接毁掉评审印象。因此多级降级链路（高德POI → DDG联网 → 离线mock）和规则兜底 Markdown 不是过度设计，而是核心需求。

**How to apply:**
- 修改任何链路代码时，必须保证最坏情况下 mock + 规则兜底仍能输出结构完整的 Markdown 推荐表
- 异常捕获宁可放宽（routes.py 已用 `except Exception` 统一兜底），也不要让任何异常冒泡成 500
- DDG 对中文本地生活搜索召回质量有限，所有 DDG 抽取值需过合理性校验（评分≥3.0、人均≥10元），否则置空降级
- 截至 2026-10-31：DEEPSEEK_API_KEY 与 AMAP_KEY 均为占位符未配置，LLM 链路走规则兜底，搜索走 DDG→mock；用户填入真实 Key 后才激活 AI 推荐链路