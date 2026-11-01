# 知途 · AI 出行与消费性价比决策 Agent

> 全国人工智能应用创新大赛参赛项目
> 定位 → 联网搜索真实门店 → 大模型性价比打分 → 可执行的出行消费方案

## 一、快速开始（Windows）

```bat
cd /d E:\consumer-agent-mastering
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
REM 用记事本打开 .env，填入 DEEPSEEK_API_KEY
python app.py
```

浏览器打开 **http://127.0.0.1:5000**
（必须用 `127.0.0.1` 或 `localhost`，否则浏览器会禁用定位）

## 二、环境变量配置

| 变量 | 必填 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | 是 | `deepseek`（云端）或 `ollama`（本地） |
| `DEEPSEEK_API_KEY` | 云端必填 | https://platform.deepseek.com 创建 |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-chat`，可选 `deepseek-reasoner` |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | 本地时 | 默认 `http://localhost:11434` / `qwen2.5:7b` |
| `AMAP_KEY` | 强烈建议 | 高德 Web 服务 Key，免费额度，国内 POI 数据最准 |
| `SEARCH_PROVIDER` | 否 | `auto` / `amap` / `ddg` / `mock` |
| `SEARCH_RADIUS_M` | 否 | 搜索半径，默认 5000 米 |

**三种运行模式**

| 模式 | 配置 | 效果 |
|---|---|---|
| 完全体 | DeepSeek + 高德 | 真实门店 + AI 分析（比赛演示用这个） |
| 免费体 | DeepSeek + 无高德 | 走 DuckDuckGo（无需 Key） |
| 断网兜底 | 无 Key | 离线演示数据 + 规则引擎打分，页面不白屏 |

配置是否生效，直接访问 `http://127.0.0.1:5000/api/agent/status` 查看。

## 三、目录结构

```
consumer-agent-mastering/
├─ app.py                      Flask 入口
├─ routes.py                   /api/agent/recommend 核心接口
├─ config.py                   环境变量集中配置
├─ prompts/system_prompt.py    Agent 系统提示词（评分口径 + 输出格式）
├─ services/
│   ├─ geo.py                  逆地理编码（高德 → OSM 兜底）
│   ├─ llm.py                  DeepSeek / Ollama 统一客户端
│   └─ search/
│       ├─ __init__.py         搜索门面（amap → ddg → mock 降级链）
│       ├─ base.py             Place 数据模型 + 文本字段抽取
│       ├─ amap.py             高德 POI 周边搜索
│       ├─ duckduckgo.py       DuckDuckGo 免费搜索（库 / HTML 双实现）
│       └─ mock.py             离线演示数据
├─ templates/index.html        页面
└─ static/                     css / js
```

## 四、接口说明

### `POST /api/agent/recommend`

请求：
```json
{ "query": "周末想去周边吃顿好的，预算100", "lat": 30.659, "lng": 104.063 }
```
也支持只用地址：`{ "query": "...", "address": "成都市武侯区" }`

响应：
```json
{
  "ok": true,
  "answer": "### 🎯 最优推荐：...（Markdown）",
  "places": [{ "name": "...", "rating": 4.7, "avg_cost": 88, "distance_text": "0.9km", "source": "高德地图" }],
  "location": { "address": "四川省成都市武侯区", "source": "高德逆地理" },
  "budget": 100,
  "meta": { "llm": "DeepSeek·deepseek-chat", "search_provider": "高德地图 POI（实时）", "elapsed_ms": 8421, "fallback": false }
}
```

### 其他
- `GET /api/health` 健康检查
- `GET /api/agent/status` 依赖配置自检

## 五、接入新的搜索源（如 dsh-free-search）

新增一个文件即可，无需改业务代码：

```python
# services/search/my_channel.py
from .base import Place

def search(query, lat=None, lng=None, address="", limit=5, **_):
    # 调用你的搜索能力，返回 Place 列表
    return [Place(name="...", rating=4.6, avg_cost=68, distance_m=900, source="my_channel")]
```

然后在 `services/search/__init__.py` 的 `_build_chain()` 里把 `"my_channel"` 加进链路、
在 `search_places()` 的分支里调用即可。

## 六、已知限制

1. 浏览器定位要求 `127.0.0.1` / `localhost` / HTTPS，局域网 IP 访问会被浏览器拦截（页面上有明确提示，并提供手动输入兜底）。
2. OSM Nominatim 有速率限制，仅作兜底，正式演示请配 `AMAP_KEY`。
3. 高德 POI 不返回 C 端详情页链接，`url` 字段可能为空，前端会自动隐藏。
4. DuckDuckGo 在国内网络可能被限流，此时会自动降级到离线数据，并在页面「降级记录」中写明原因。
