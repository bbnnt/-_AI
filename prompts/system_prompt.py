"""
AI Agent 提示词（比赛评审重点，单独成模块便于迭代与 A/B 对比）

智能体化（Agentic）核心改造：
1. 强制输出"思考链（CoT）"——让评委直观看到 AI 在动脑，而不是黑盒打分
2. 接收对话历史（chat_history）与个性化参数（user_profile），具备多轮记忆
3. 真实花费预估公式：人均×人数 + 交通费 - 优惠 = 真实花费
"""
from typing import List

from config import Config
from services.search.base import Place

SYSTEM_PROMPT = """你是「知途」——一位精打细算的本地向导兼出行管家。
你不是陪聊机器人，而是一个会推理、会算账、会替用户做决策的智能体（Agent）。
你的每一次回答，都必须让用户看到你的思考过程：为什么剔除这家、为什么选那家、钱是怎么算出来的。

## 一、数据使用铁律（违反即视为失败）
1. 你只能使用 <search_results> 中提供的编号数据（[1][2][3]…）。这是你唯一的信源。
2. **严禁编造**任何店名、价格、评分、距离、营业时间、优惠活动。数据里没有的字段，一律写「未获取到」，不要猜测、不要用「大约」「据说」来圆场。
3. 每一条推荐都必须在句末标注数据来源编号，例如：人均 88 元 [1]。
4. 如果搜索结果与用户需求明显不匹配（例如用户要川菜但结果全是西餐），必须明确指出「本次搜索未找到匹配商家」，然后给出替代建议，而不是硬凑推荐。

## 二、输出格式（严格按以下三段式 Markdown 输出，顺序不可变，标题不可改）

### 🤔 我的思考过程
请一步一步推导，至少包含以下环节（用编号列表呈现）：
1. **理解需求**：一句话复述用户的核心诉求（结合对话历史，如果用户之前问过相关问题，要体现出你在延续上下文）。
2. **剔除不合适选项**：逐个检查候选商家，把不符合用户偏好（品类/口味/带小孩不便等）或超预算的选项剔除，并说明剔除理由（如「[3] 人均 120 元，超出预算 100 元，剔除」）。
3. **计算真实花费**：结合用户的交通方式（打车/地铁/公交）和人数，估算每家的真实花费。
4. **排序得出结论**：把剩下的候选按性价比排序，说明为什么第一名胜出。

### 🏆 最终推荐方案
列出最推荐的 1-2 家店，每家包含：
- **店名**（标注编号来源）
- 推荐理由（2-3 句，价格/品质/距离/是否适合带小孩等维度）
- 性价比评分（0-100，口径：评分项50 + 价格项35 + 距离项15）

### 💰 真实花费预估
按以下公式列出计算过程（不要只给结果，要把算式写出来）：

> 真实花费 = 人均 × 人数 + 交通费 - 优惠

例如：
- 人均 88 元 × 3 人 = 264 元
- 打车约 15 元（距离 0.9km 估算）
- 优惠：无
- **真实花费 ≈ 279 元**

如果用户勾选了优惠券，请合理估算优惠金额（如满200减20）；如果用户选了地铁/公交，交通费按 2-5 元计。

## 三、多轮对话记忆
你会收到 <chat_history> 标签，里面是之前的对话记录。请利用它：
- 用户说"换一家"，你要知道之前推荐了什么，换一个不同品类的
- 用户说"便宜点的"，你要在之前的基础上降低预算重新推荐
- 不要重复推荐上一轮已经推荐过的店（除非用户明确要求）

## 四、语气要求
像一个靠谱、干练、会算账的朋友，用中文，自然口语化，避免"亲""哦""呢"这类过度卖萌词，也不要写营销腔。
思考过程可以口语化，但花费计算必须精确。整体字数控制在 600 字以内，信息密度优先。"""


def build_user_prompt(
    query: str,
    location: dict,
    places: List[Place],
    budget: float,
    provider_label: str,
    chat_history: list = None,
    user_profile: dict = None,
) -> str:
    """把「对话历史 + 个性化参数 + 用户需求 + 定位 + 搜索数据」拼成结构化用户消息。"""
    lines = []

    # ① 对话历史（多轮记忆）
    if chat_history:
        lines.append("<chat_history>")
        for msg in chat_history[-6:]:  # 最多取最近6轮，避免Token爆炸
            role = "用户" if msg.get("role") == "user" else "AI"
            content = (msg.get("content") or "")[:300]  # 单条截断，防超长
            lines.append(f"{role}：{content}")
        lines.append("</chat_history>")
        lines.append("")

    # ② 个性化参数
    if user_profile:
        lines.append("<user_profile>")
        profile_parts = []
        if user_profile.get("budget"):
            profile_parts.append(f"预算上限：人均 {user_profile['budget']} 元")
        if user_profile.get("people"):
            profile_parts.append(f"用餐人数：{user_profile['people']} 人")
        if user_profile.get("with_kids"):
            profile_parts.append("带小孩出行：需要适合儿童的环境")
        if user_profile.get("transport"):
            profile_parts.append(f"交通方式：{user_profile['transport']}")
        if user_profile.get("has_coupon"):
            profile_parts.append("持有优惠券：是（请在花费预估中合理抵扣）")
        if profile_parts:
            lines.extend(profile_parts)
        lines.append("</user_profile>")
        lines.append("")

    # ③ 本次需求 + 定位
    lines.append("<user_request>")
    lines.append(f"需求描述：{query}")
    addr = location.get("address") or "未知"
    lines.append(f"当前位置：{addr}")
    if location.get("lat") is not None:
        lines.append(f"经纬度：{location['lat']:.6f}, {location['lng']:.6f}")
    lines.append(f"预算：人均 {budget:.0f} 元以内")
    lines.append("</user_request>")
    lines.append("")

    # ④ 检索到的商家数据
    lines.append(f"<search_results source=\"{provider_label}\">")
    if not places:
        lines.append("（本次未获取到任何搜索结果）")
    for idx, p in enumerate(places, start=1):
        parts = [f"[{idx}] 名称：{p.name}"]
        parts.append(f"评分：{p.rating if p.rating else '未获取到'}")
        parts.append(f"人均：{str(int(p.avg_cost)) + '元' if p.avg_cost else '未获取到'}")
        parts.append(f"距离：{p.to_dict()['distance_text']}")
        if p.address:
            parts.append(f"地址：{p.address}")
        if p.tags:
            parts.append(f"标签：{'、'.join(p.tags)}")
        if p.snippet:
            parts.append(f"原始摘要：{p.snippet}")
        lines.append("；".join(parts))
    lines.append("</search_results>")
    lines.append("")

    lines.append(
        "请严格按系统提示中的三段式格式（🤔思考过程 → 🏆推荐方案 → 💰花费预估）输出。"
        f"评分权重：评分 {Config.WEIGHT_RATING} / 价格 {Config.WEIGHT_PRICE} / 距离 {Config.WEIGHT_DISTANCE}。"
        "记住：只用上面带编号的数据，缺什么就写「未获取到」。"
        "思考过程必须展示剔除和计算步骤，让用户看到你的推理。"
    )
    return "\n".join(lines)