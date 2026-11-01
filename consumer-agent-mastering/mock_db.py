"""
# ============================================================
#  知途 · 本地商家 Mock 数据源（演示阶段专用）
# ============================================================
#
#  为什么不用 DuckDuckGo 免费搜索？
#    1. 召回大量垃圾/资讯网站（百科、视频站、政务页），严重影响演示效果；
#    2. 网页摘要数据残缺，无法稳定提取「店名 / 距离 / 人均 / 评分」四要素，
#       导致性价比打分失去区分度。
#
#  本文件方案：「Mock 数据 + 真实接口预留」
#    - 演示阶段：get_mock_places() 返回结构完整的 5 条商家数据，保证演示效果；
#    - 上线阶段：将 routes.py 中的调用替换为高德地图 API
#      （请求代码框架见本文件底部注释，完整实现见 services/search/amap.py）。
# ============================================================
"""
import random
from typing import Dict, List


# ============================================================
#  品类数据集
#  字段说明：
#    name     店名
#    distance 距离（展示格式，如 "1.2km" / "600m"）
#    rating   评分（满分 5）
#    cost     人均消费（如 "85元"）
#    address  地址
#    category 品类
#    tags     标签（供大模型参考的特色描述）
# ============================================================
_DATASET_CHUANCAI = [
    {"name": "老李川菜馆（招牌店）", "distance": "1.2km", "rating": 4.8, "cost": "85元",
     "address": "武侯区科华北路 12 号", "category": "川菜", "tags": ["招牌水煮鱼", "本地人常去", "分量足"]},
    {"name": "巷子口冒菜（玉林店）", "distance": "0.8km", "rating": 4.5, "cost": "42元",
     "address": "武侯区玉林横街 5 号附 3", "category": "川菜", "tags": ["一人食友好", "上菜快", "老店"]},
    {"name": "蓉城印象·家常川菜", "distance": "2.1km", "rating": 4.3, "cost": "65元",
     "address": "青羊区光华村街 66 号", "category": "川菜", "tags": ["有包间", "适合聚餐"]},
    {"name": "陈麻婆豆腐（总店）", "distance": "3.0km", "rating": 4.6, "cost": "78元",
     "address": "青羊区西玉龙街 197 号", "category": "川菜", "tags": ["老字号", "味道正宗"]},
    {"name": "江湖菜馆（建设路店）", "distance": "1.5km", "rating": 4.1, "cost": "108元",
     "address": "成华区建设路 33 号", "category": "川菜", "tags": ["环境好", "略贵", "适合请客"]},
    {"name": "蜀香居·老成都川菜馆", "distance": "0.9km", "rating": 4.7, "cost": "88元",
     "address": "武侯区科华北路 12 号", "category": "川菜", "tags": ["招牌水煮鱼", "分量足", "免费米饭"]},
    {"name": "巴国布衣（武侯祠店）", "distance": "2.5km", "rating": 4.4, "cost": "95元",
     "address": "武侯区武侯祠大街 23 号", "category": "川菜", "tags": ["文化主题", "适合游客", "有表演"]},
    {"name": "自贡盐帮菜·鲜锅兔", "distance": "1.8km", "rating": 4.5, "cost": "70元",
     "address": "锦江区莲桂南路 8 号", "category": "川菜", "tags": ["盐帮菜", "鲜辣", "本地人推荐"]},
    {"name": "宽窄巷子·私房川菜", "distance": "2.8km", "rating": 4.2, "cost": "128元",
     "address": "青羊区宽窄巷子 12 号", "category": "川菜", "tags": ["环境雅致", "私房菜", "略贵"]},
]

_DATASET_HOTPOT = [
    {"name": "蜀九香火锅（玉林店）", "distance": "1.4km", "rating": 4.7, "cost": "98元",
     "address": "武侯区玉林中路 8 号", "category": "火锅", "tags": ["牛油锅底", "鲜毛肚", "排队多"]},
    {"name": "钢管厂五区小郡肝串串", "distance": "0.9km", "rating": 4.4, "cost": "55元",
     "address": "锦江区水碾河路 26 号", "category": "火锅", "tags": ["性价比高", "串串自助"]},
    {"name": "小龙坎老火锅（春熙路店）", "distance": "2.3km", "rating": 4.2, "cost": "115元",
     "address": "锦江区春熙路南段 8 号", "category": "火锅", "tags": ["环境好", "适合聚餐", "略贵"]},
    {"name": "市井老灶火锅", "distance": "1.8km", "rating": 4.5, "cost": "72元",
     "address": "成华区双林路 45 号", "category": "火锅", "tags": ["老灶风味", "锅底香"]},
    {"name": "潮汕牛肉火锅（社区店）", "distance": "0.6km", "rating": 4.3, "cost": "88元",
     "address": "武侯区一环路南一段 9 号", "category": "火锅", "tags": ["现切牛肉", "清淡不上火"]},
    {"name": "大龙燚火锅（玉林店）", "distance": "1.6km", "rating": 4.4, "cost": "92元",
     "address": "武侯区玉林东路 8 号", "category": "火锅", "tags": ["重口味牛油", "深夜营业"]},
    {"name": "楠火锅（太古里店）", "distance": "2.0km", "rating": 4.5, "cost": "105元",
     "address": "锦江区中纱帽街 6 号", "category": "火锅", "tags": ["网红店", "甜品解辣", "排队多"]},
    {"name": "电台巷火锅（建设路店）", "distance": "1.3km", "rating": 4.6, "cost": "78元",
     "address": "成华区建设巷 11 号", "category": "火锅", "tags": ["市井风", "性价比高", "锅底香"]},
]

_DATASET_COFFEE = [
    {"name": "拾光咖啡（社区店）", "distance": "0.5km", "rating": 4.6, "cost": "32元",
     "address": "武侯区一环路南一段 3 号", "category": "咖啡", "tags": ["安静", "有插座", "手冲"]},
    {"name": "Manner Coffee（来福士店）", "distance": "1.0km", "rating": 4.4, "cost": "25元",
     "address": "武侯区人民南路四段 3 号", "category": "咖啡", "tags": ["性价比高", "出餐快"]},
    {"name": "星巴克（太古里店）", "distance": "2.2km", "rating": 4.2, "cost": "45元",
     "address": "锦江区中纱帽街 8 号", "category": "咖啡", "tags": ["环境好", "适合办公"]},
    {"name": "独立书房咖啡馆", "distance": "1.6km", "rating": 4.7, "cost": "38元",
     "address": "青羊区奎星楼街 22 号", "category": "咖啡", "tags": ["文艺", "甜品不错", "座位少"]},
    {"name": "瑞幸咖啡（写字楼店）", "distance": "0.3km", "rating": 4.1, "cost": "18元",
     "address": "附近写字楼 1F", "category": "咖啡", "tags": ["便宜", "自提快"]},
    {"name": "Peet's Coffee（太古里店）", "distance": "2.4km", "rating": 4.5, "cost": "42元",
     "address": "锦江区中纱帽街 8 号", "category": "咖啡", "tags": ["深度烘焙", "美式好喝"]},
    {"name": "Seesaw Coffee（万象城店）", "distance": "2.9km", "rating": 4.4, "cost": "38元",
     "address": "成华区双庆路 8 号", "category": "咖啡", "tags": ["创意特调", "适合拍照"]},
    {"name": "社区角落·手冲小馆", "distance": "0.7km", "rating": 4.8, "cost": "45元",
     "address": "武侯区郭家桥北街 5 号", "category": "咖啡", "tags": ["手冲精品", "老板懂豆", "座位极少"]},
]

_DATASET_BARBECUE = [
    {"name": "老铁烧烤（建设路店）", "distance": "1.5km", "rating": 4.5, "cost": "68元",
     "address": "成华区建设路 33 号", "category": "烧烤", "tags": ["分量大", "营业到凌晨"]},
    {"name": "何师烧烤（玉林店）", "distance": "1.1km", "rating": 4.3, "cost": "75元",
     "address": "武侯区玉林南路 10 号", "category": "烧烤", "tags": ["烤鱼一绝", "环境一般"]},
    {"name": "把把烧（宽窄巷子店）", "distance": "2.6km", "rating": 4.1, "cost": "95元",
     "address": "青羊区宽窄巷子东侧", "category": "烧烤", "tags": ["游客多", "略贵"]},
    {"name": "东北烤串小院", "distance": "0.7km", "rating": 4.6, "cost": "50元",
     "address": "成华区新鸿路 18 号", "category": "烧烤", "tags": ["便宜量足", "锡纸金针菇"]},
    {"name": "深夜食堂·烤肉屋", "distance": "1.9km", "rating": 4.4, "cost": "82元",
     "address": "锦江区东大街 88 号", "category": "烧烤", "tags": ["日式烤肉", "肉质好"]},
    {"name": "峨眉烧烤（总店）", "distance": "1.4km", "rating": 4.3, "cost": "58元",
     "address": "武侯区一环路南二段 10 号", "category": "烧烤", "tags": ["乐山风味", "烤五花肉一绝"]},
    {"name": "新疆红柳烤肉", "distance": "2.2km", "rating": 4.5, "cost": "65元",
     "address": "锦江区莲桂西路 18 号", "category": "烧烤", "tags": ["红柳枝烤串", "大盘鸡", "异域风味"]},
    {"name": "烤匠·麻辣烤鱼（春熙路店）", "distance": "2.6km", "rating": 4.6, "cost": "88元",
     "address": "锦江区春熙路南段 10 号", "category": "烧烤", "tags": ["烤鱼", "麻辣味", "成都必吃"]},
]

_DATASET_JAPANESE = [
    {"name": "鮨·匠心寿司（太古里店）", "distance": "1.8km", "rating": 4.8, "cost": "168元",
     "address": "锦江区中纱帽街 8 号", "category": "日料", "tags": ["Omakase", "食材新鲜", "需预约"]},
    {"name": "居酒屋·深夜一番", "distance": "1.2km", "rating": 4.5, "cost": "95元",
     "address": "武侯区科华北路 50 号", "category": "日料", "tags": ["烤串", "清酒", "氛围好"]},
    {"name": "一兰拉面（春熙路店）", "distance": "2.0km", "rating": 4.3, "cost": "58元",
     "address": "锦江区春熙路南段 12 号", "category": "日料", "tags": ["豚骨汤底", "一人食", "排队多"]},
    {"name": "和风食堂·定食屋", "distance": "0.9km", "rating": 4.4, "cost": "48元",
     "address": "武侯区一环路南二段 15 号", "category": "日料", "tags": ["定食套餐", "性价比高"]},
    {"name": "刺身工坊（社区店）", "distance": "1.5km", "rating": 4.1, "cost": "128元",
     "address": "成华区建设路 66 号", "category": "日料", "tags": ["刺身拼盘", "略贵"]},
    {"name": "元气寿司·回转寿司", "distance": "1.0km", "rating": 4.2, "cost": "65元",
     "address": "武侯区来福士 B1", "category": "日料", "tags": ["回转寿司", "性价比高", "一人食"]},
    {"name": "鸟贵族·居酒屋（玉林店）", "distance": "0.8km", "rating": 4.6, "cost": "85元",
     "address": "武侯区玉林中路 12 号", "category": "日料", "tags": ["烧鸟", "清酒", "氛围绝佳"]},
    {"name": "味噌拉面·博多一幸舍", "distance": "1.7km", "rating": 4.3, "cost": "52元",
     "address": "锦江区春熙路 IFS B2", "category": "日料", "tags": ["豚骨拉面", "可加面", "排队适中"]},
]

_DATASET_WESTERN = [
    {"name": "王品牛排（仁恒店）", "distance": "2.5km", "rating": 4.7, "cost": "368元",
     "address": "锦江区人民南路二段 1 号", "category": "西餐", "tags": ["高端", "适合纪念日", "服务好"]},
    {"name": "萨莉亚意式餐厅（来福士店）", "distance": "1.1km", "rating": 4.2, "cost": "45元",
     "address": "武侯区人民南路四段 3 号", "category": "西餐", "tags": ["便宜", "意面", "家庭友好"]},
    {"name": "蓝蛙西餐厅（太古里店）", "distance": "1.9km", "rating": 4.4, "cost": "135元",
     "address": "锦江区中纱帽街 8 号", "category": "西餐", "tags": ["汉堡", "环境好", "适合聚会"]},
    {"name": "街角披萨小馆", "distance": "0.8km", "rating": 4.5, "cost": "68元",
     "address": "武侯区玉林东路 22 号", "category": "西餐", "tags": ["手工披萨", "外送快", "性价比高"]},
    {"name": "法式小酒馆·Bistro", "distance": "1.6km", "rating": 4.6, "cost": "198元",
     "address": "青羊区奎星楼街 18 号", "category": "西餐", "tags": ["红酒", "氛围好", "略贵"]},
    {"name": "必胜客（来福士店）", "distance": "1.1km", "rating": 4.0, "cost": "75元",
     "address": "武侯区人民南路四段 3 号", "category": "西餐", "tags": ["披萨", "家庭友好", "稳定"]},
    {"name": "Wagas 沃歌斯（太古里店）", "distance": "2.1km", "rating": 4.3, "cost": "85元",
     "address": "锦江区中纱帽街 8 号", "category": "西餐", "tags": ["轻食沙拉", "健康", "早午餐"]},
    {"name": "彼得家厨房·牛排馆", "distance": "2.7km", "rating": 4.5, "cost": "288元",
     "address": "锦江区红星路三段 IFS 5F", "category": "西餐", "tags": ["干式熟成牛排", "高端", "纪念日"]},
]

_DATASET_CANTONESE = [
    {"name": "利苑酒家（IFS店）", "distance": "2.2km", "rating": 4.7, "cost": "220元",
     "address": "锦江区红星路三段 1 号", "category": "粤菜", "tags": ["米其林", "早茶", "高端"]},
    {"name": "翠华茶餐厅（春熙路店）", "distance": "1.7km", "rating": 4.3, "cost": "75元",
     "address": "锦江区春熙路北段 30 号", "category": "粤菜", "tags": ["港式奶茶", "菠萝油"]},
    {"name": "顺德菜·猪杂粥底火锅", "distance": "1.3km", "rating": 4.5, "cost": "88元",
     "address": "武侯区航空路 10 号", "category": "粤菜", "tags": ["粥底火锅", "食材新鲜"]},
    {"name": "港式烧腊快餐店", "distance": "0.7km", "rating": 4.2, "cost": "38元",
     "address": "武侯区一环路南一段 28 号", "category": "粤菜", "tags": ["叉烧饭", "便宜", "上菜快"]},
    {"name": "点都德·广式早茶（万象城店）", "distance": "2.8km", "rating": 4.6, "cost": "92元",
     "address": "成华区双庆路 8 号", "category": "粤菜", "tags": ["虾饺", "早茶必去", "排队多"]},
    {"name": "陶陶居酒家（春熙路店）", "distance": "2.0km", "rating": 4.5, "cost": "105元",
     "address": "锦江区春熙路 IFS 6F", "category": "粤菜", "tags": ["百年老字号", "烧鹅", "广式点心"]},
    {"name": "潮汕砂锅粥（玉林店）", "distance": "1.2km", "rating": 4.4, "cost": "68元",
     "address": "武侯区玉林南路 15 号", "category": "粤菜", "tags": ["砂锅粥", "生腌", "夜宵好去处"]},
]

_DATASET_NOODLES = [
    {"name": "老王砂锅米线（总店）", "distance": "0.9km", "rating": 4.6, "cost": "28元",
     "address": "武侯区一环路南一段 20 号", "category": "面食小吃", "tags": ["汤底浓", "一人食友好", "便宜"]},
    {"name": "兰州拉面（社区店）", "distance": "0.4km", "rating": 4.1, "cost": "22元",
     "address": "武侯区磨子桥 4 巷", "category": "面食小吃", "tags": ["牛肉面", "分量足", "便宜"]},
    {"name": "螺蛳粉·柳州味道", "distance": "1.0km", "rating": 4.4, "cost": "25元",
     "address": "锦江区水碾河路 12 号", "category": "面食小吃", "tags": ["重口味", "人气高"]},
    {"name": "东北饺子馆（玉林店）", "distance": "1.2km", "rating": 4.5, "cost": "32元",
     "address": "武侯区玉林正街 9 号", "category": "面食小吃", "tags": ["手工饺", "分量足"]},
    {"name": "抄手担担面·老字号", "distance": "0.6km", "rating": 4.3, "cost": "20元",
     "address": "青羊区人民中路三段 5 号", "category": "面食小吃", "tags": ["担担面", "红油抄手", "本地老店"]},
    {"name": "重庆小面（社区店）", "distance": "0.5km", "rating": 4.4, "cost": "18元",
     "address": "武侯区郭家桥正街 2 号", "category": "面食小吃", "tags": ["豌豆炸酱面", "便宜", "早上就开门"]},
    {"name": "甘食记·肥肠粉", "distance": "1.1km", "rating": 4.5, "cost": "25元",
     "address": "锦江区东大街 66 号", "category": "面食小吃", "tags": ["肥肠粉", "冒节子", "成都名小吃"]},
    {"name": "袁记云饺（玉林店）", "distance": "0.8km", "rating": 4.2, "cost": "22元",
     "address": "武侯区玉林北路 10 号", "category": "面食小吃", "tags": ["现包云吞", "皮薄馅大", "干净"]},
]

_DATASET_DESSERT = [
    {"name": "好利来蛋糕（春熙路店）", "distance": "1.8km", "rating": 4.4, "cost": "42元",
     "address": "锦江区春熙路南段 15 号", "category": "甜品烘焙", "tags": ["半熟芝士", "包装精美"]},
    {"name": "手工面包坊·麦香", "distance": "0.8km", "rating": 4.6, "cost": "35元",
     "address": "武侯区玉林北路 6 号", "category": "甜品烘焙", "tags": ["欧包", "现烤", "早去才有"]},
    {"name": "满记甜品（来福士店）", "distance": "1.3km", "rating": 4.2, "cost": "48元",
     "address": "武侯区人民南路四段 3 号", "category": "甜品烘焙", "tags": ["杨枝甘露", "连锁稳定"]},
    {"name": "法式甜品·小苍兰", "distance": "1.6km", "rating": 4.8, "cost": "68元",
     "address": "青羊区泡桐树街 12 号", "category": "甜品烘焙", "tags": ["精致", "适合拍照", "略贵"]},
    {"name": "社区蛋挞王", "distance": "0.5km", "rating": 4.5, "cost": "15元",
     "address": "武侯区科华北路 60 号", "category": "甜品烘焙", "tags": ["现烤蛋挞", "便宜", "排队"]},
]

_DATASET_BUFFET = [
    {"name": "四海一家国际自助（万达店）", "distance": "2.4km", "rating": 4.3, "cost": "158元",
     "address": "锦江区锦华路三段 1 号", "category": "自助餐", "tags": ["品类多", "海鲜", "适合聚餐"]},
    {"name": "汉拿山烤肉自助", "distance": "1.5km", "rating": 4.1, "cost": "98元",
     "address": "成华区建设路 33 号", "category": "自助餐", "tags": ["烤肉畅吃", "性价比高"]},
    {"name": "上井精致料理自助", "distance": "2.8km", "rating": 4.6, "cost": "268元",
     "address": "锦江区红星路三段 1 号", "category": "自助餐", "tags": ["日料自助", "刺身畅吃", "略贵"]},
    {"name": "火锅自助·大口吃", "distance": "1.0km", "rating": 4.0, "cost": "78元",
     "address": "武侯区一环路南一段 18 号", "category": "自助餐", "tags": ["便宜", "锅底任选", "环境一般"]},
    {"name": "海鲜自助·蓝海国际", "distance": "3.2km", "rating": 4.5, "cost": "218元",
     "address": "青羊区光华大道 1 号", "category": "自助餐", "tags": ["鲜活海鲜", "帝王蟹", "适合请客"]},
]

_DATASET_KOREAN = [
    {"name": "姜虎东白丁烤肉（太古里店）", "distance": "1.9km", "rating": 4.5, "cost": "128元",
     "address": "锦江区中纱帽街 8 号", "category": "韩餐", "tags": ["韩式烤肉", "小菜多", "排队多"]},
    {"name": "本家韩国料理", "distance": "1.4km", "rating": 4.3, "cost": "88元",
     "address": "武侯区科华北路 62 号", "category": "韩餐", "tags": ["石锅拌饭", "部队锅", "分量足"]},
    {"name": "首尔大排档·炸鸡啤酒", "distance": "1.1km", "rating": 4.4, "cost": "72元",
     "address": "锦江区东大街 56 号", "category": "韩餐", "tags": ["炸鸡", "啤酒", "夜宵好去处"]},
    {"name": "部队锅·欧巴的小厨房", "distance": "0.8km", "rating": 4.2, "cost": "65元",
     "address": "武侯区玉林南路 3 号", "category": "韩餐", "tags": ["部队锅", "起司拉丝", "性价比高"]},
    {"name": "韩式炸酱面馆", "distance": "1.7km", "rating": 4.0, "cost": "38元",
     "address": "成华区新鸿路 25 号", "category": "韩餐", "tags": ["炸酱面", "便宜", "上菜快"]},
]

_DATASET_FASTFOOD = [
    {"name": "麦当劳（春熙路店）", "distance": "1.6km", "rating": 4.0, "cost": "35元",
     "address": "锦江区春熙路北段 20 号", "category": "简餐快餐", "tags": ["出餐快", "稳定", "24h"]},
    {"name": "乡村基（来福士店）", "distance": "1.2km", "rating": 4.2, "cost": "28元",
     "address": "武侯区人民南路四段 3 号", "category": "简餐快餐", "tags": ["中式快餐", "便宜", "套餐多"]},
    {"name": "沙县小吃（社区店）", "distance": "0.4km", "rating": 3.9, "cost": "18元",
     "address": "武侯区磨子桥 7 巷", "category": "简餐快餐", "tags": ["最便宜", "炖罐", "上菜快"]},
    {"name": "吉野家（写字楼店）", "distance": "0.6km", "rating": 4.1, "cost": "32元",
     "address": "附近写字楼 B1", "category": "简餐快餐", "tags": ["牛肉饭", "工作日午餐", "自提快"]},
    {"name": "真功夫·蒸品快餐", "distance": "1.0km", "rating": 4.0, "cost": "30元",
     "address": "锦江区东大街 99 号", "category": "简餐快餐", "tags": ["蒸菜", "相对健康", "套餐"]},
]

_DATASET_HUNAN = [
    {"name": "费大厨辣椒炒肉（春熙路店）", "distance": "2.1km", "rating": 4.6, "cost": "78元",
     "address": "锦江区春熙路 IFS B1", "category": "湘菜", "tags": ["辣椒炒肉", "湘菜头部", "排队多"]},
    {"name": "笨萝卜浏阳菜馆", "distance": "1.5km", "rating": 4.5, "cost": "65元",
     "address": "武侯区科华北路 80 号", "category": "湘菜", "tags": ["蒸菜", "剁椒鱼头", "下饭"]},
    {"name": "湘西部落·土家菜", "distance": "2.4km", "rating": 4.3, "cost": "88元",
     "address": "成华区建设路 50 号", "category": "湘菜", "tags": ["腊肉", "土钵菜", "分量足"]},
    {"name": "炊烟小炒黄牛肉（万象城店）", "distance": "2.9km", "rating": 4.4, "cost": "82元",
     "address": "成华区双庆路 8 号", "category": "湘菜", "tags": ["小炒黄牛肉", "网红湘菜"]},
    {"name": "老长沙龙虾馆", "distance": "1.8km", "rating": 4.2, "cost": "95元",
     "address": "锦江区莲桂南路 20 号", "category": "湘菜", "tags": ["口味虾", "夜宵", "辣度可选"]},
]

_DATASET_DONGBEI = [
    {"name": "东北人家·铁锅炖（建设路店）", "distance": "1.6km", "rating": 4.5, "cost": "72元",
     "address": "成华区建设路 42 号", "category": "东北菜", "tags": ["铁锅炖大鹅", "分量超大", "适合聚餐"]},
    {"name": "老边饺子馆（春熙路店）", "distance": "2.0km", "rating": 4.4, "cost": "48元",
     "address": "锦江区春熙路北段 22 号", "category": "东北菜", "tags": ["百年老字号", "蒸饺", "性价比高"]},
    {"name": "灶台鱼·东北私房菜", "distance": "2.3km", "rating": 4.3, "cost": "85元",
     "address": "武侯区航空路 6 号", "category": "东北菜", "tags": ["灶台鱼", "贴饼子", "东北氛围"]},
    {"name": "翠花餐厅·酸菜白肉", "distance": "1.2km", "rating": 4.2, "cost": "55元",
     "address": "成华区新鸿路 30 号", "category": "东北菜", "tags": ["酸菜白肉", "锅包肉", "家常味"]},
    {"name": "小鸡炖蘑菇·农家院", "distance": "2.7km", "rating": 4.1, "cost": "68元",
     "address": "锦江区三圣乡 88 号", "category": "东北菜", "tags": ["柴火灶", "农家菜", "远离市中心"]},
]

_DATASET_MILKTEA = [
    {"name": "茶百道（春熙路店）", "distance": "1.7km", "rating": 4.3, "cost": "18元",
     "address": "锦江区春熙路南段 8 号", "category": "奶茶饮品", "tags": ["杨枝甘露", "性价比高", "出杯快"]},
    {"name": "喜茶（太古里店）", "distance": "2.2km", "rating": 4.5, "cost": "28元",
     "address": "锦江区中纱帽街 8 号", "category": "奶茶饮品", "tags": ["多肉葡萄", "网红", "排队多"]},
    {"name": "霸王茶姬（万象城店）", "distance": "2.8km", "rating": 4.4, "cost": "20元",
     "address": "成华区双庆路 8 号", "category": "奶茶饮品", "tags": ["伯牙绝弦", "国风", "低糖可选"]},
    {"name": "书亦烧仙草（玉林店）", "distance": "0.9km", "rating": 4.2, "cost": "15元",
     "address": "武侯区玉林中路 5 号", "category": "奶茶饮品", "tags": ["烧仙草", "便宜", "社区店"]},
    {"name": "奈雪的茶（来福士店）", "distance": "1.1km", "rating": 4.4, "cost": "25元",
     "address": "武侯区人民南路四段 3 号", "category": "奶茶饮品", "tags": ["霸气橙子", "欧包搭配", "环境好"]},
]

# 默认数据集：需求未命中任何品类时使用（通用美食/家常）
_DATASET_DEFAULT = [
    {"name": "老李川菜馆（招牌店）", "distance": "1.2km", "rating": 4.8, "cost": "85元",
     "address": "武侯区科华北路 12 号", "category": "餐饮", "tags": ["招牌水煮鱼", "本地人常去"]},
    {"name": "社区食堂（平价档）", "distance": "0.6km", "rating": 4.2, "cost": "35元",
     "address": "附近社区服务中心 1F", "category": "餐饮", "tags": ["便宜", "干净", "上菜快"]},
    {"name": "本地人气家常菜馆", "distance": "1.1km", "rating": 4.5, "cost": "75元",
     "address": "附近商圈 B 区 2 楼", "category": "餐饮", "tags": ["口味家常", "分量足"]},
    {"name": "老王砂锅米线", "distance": "0.9km", "rating": 4.4, "cost": "28元",
     "address": "武侯区一环路南一段 20 号", "category": "餐饮", "tags": ["汤底浓", "一人食友好"]},
    {"name": "拾光咖啡简餐", "distance": "0.5km", "rating": 4.6, "cost": "52元",
     "address": "武侯区一环路南一段 3 号", "category": "餐饮", "tags": ["安静", "简餐不错"]},
]

# 品类关键词 -> 数据集映射（命中任一关键词即返回该数据集）
_CATEGORY_MAP: Dict[str, List[dict]] = {
    "火锅": _DATASET_HOTPOT,
    "日料": _DATASET_JAPANESE,
    "韩餐": _DATASET_KOREAN,
    "粤菜": _DATASET_CANTONESE,
    "西餐": _DATASET_WESTERN,
    "甜品烘焙": _DATASET_DESSERT,
    "自助餐": _DATASET_BUFFET,
    "面食小吃": _DATASET_NOODLES,
    "简餐快餐": _DATASET_FASTFOOD,
    "咖啡": _DATASET_COFFEE,
    "烧烤": _DATASET_BARBECUE,
    "川菜": _DATASET_CHUANCAI,
    "湘菜": _DATASET_HUNAN,
    "东北菜": _DATASET_DONGBEI,
    "奶茶饮品": _DATASET_MILKTEA,
}

# 每个数据集对应的触发关键词（口语化同义词也覆盖）
# 顺序即优先级：具体品类在前，通用兜底词（美食/中餐等）放最后的川菜组
_TRIGGER_WORDS: Dict[str, tuple] = {
    "火锅": ("火锅", "串串", "涮"),
    "日料": ("日料", "寿司", "刺身", "居酒屋", "日式"),
    "韩餐": ("韩餐", "韩式", "韩国料理", "部队锅"),
    "粤菜": ("粤菜", "茶餐厅", "早茶", "烧腊", "港式", "广东菜"),
    "湘菜": ("湘菜", "湖南菜", "辣椒炒肉", "剁椒"),
    "东北菜": ("东北菜", "东北", "铁锅炖", "锅包肉", "酸菜"),
    "奶茶饮品": ("奶茶", "饮品", "果茶", "烧仙草"),
    "西餐": ("西餐", "牛排", "意面", "披萨", "西式"),
    "甜品烘焙": ("甜品", "蛋糕", "面包", "烘焙", "甜点", "糕点"),
    "自助餐": ("自助餐", "自助", "放题"),
    "面食小吃": ("面条", "米线", "小吃", "米粉", "饺子", "包子", "馄饨", "抄手", "拉面", "面馆", "螺蛳粉"),
    "简餐快餐": ("快餐", "简餐", "盒饭", "工作餐", "午餐", "便当"),
    "咖啡": ("咖啡", "下午茶", "喝点"),
    "烧烤": ("烧烤", "夜宵", "烤串", "烤肉", "撸串"),
    "川菜": ("川菜", "川味", "辣", "冒菜", "家常菜", "中餐", "美食", "吃顿好的", "吃顿饭"),
}


def get_mock_places(location: str, keyword: str, sample_size: int = 5) -> List[dict]:
    """
    获取 Mock 商家数据（演示阶段的数据源入口）。

    智能体化改造：从品类数据池中随机采样，每次查询返回不同子集，
    避免演示时"每次都是同一批店"的僵硬感。

    :param location: 用户位置描述（如 "成都市武侯区"），目前仅用于溯源展示
    :param keyword:  需求关键词（如 "川菜" / "火锅" / "美食"）
    :param sample_size: 返回条数（默认5，数据池不足时返回全部）
    :return:         随机采样的商家字典列表
    """
    text = f"{keyword or ''} {location or ''}"

    for category, words in _TRIGGER_WORDS.items():
        if any(w in text for w in words):
            pool = _CATEGORY_MAP[category]
            picks = random.sample(pool, min(sample_size, len(pool)))
            return [dict(item) for item in picks]

    pool = _DATASET_DEFAULT
    picks = random.sample(pool, min(sample_size, len(pool)))
    return [dict(item) for item in picks]


# ============================================================
#  TODO: 未来上线时，此处替换为高德地图API
#  ------------------------------------------------------------
#  高德 Web 服务 POI 周边搜索请求框架（取消注释并配置 AMAP_KEY 即可启用）：
#
#  import requests
#
#  AMAP_KEY = "你的高德Web服务Key"          # console.amap.com 创建，选「Web服务」类型
#  AMAP_AROUND_URL = "https://restapi.amap.com/v3/place/around"
#
#  def get_real_places(lat: float, lng: float, keyword: str, radius: int = 5000) -> list:
#      """高德周边搜索：返回真实 POI（含评分/人均/距离），结构与 get_mock_places 对齐"""
#      resp = requests.get(AMAP_AROUND_URL, params={
#          "key": AMAP_KEY,
#          "location": f"{lng:.6f},{lat:.6f}",   # 高德要求 经度,纬度
#          "keywords": keyword,
#          "radius": radius,
#          "sortrule": "distance",               # 按距离由近到远
#          "extensions": "all",                  # 返回评分/人均等扩展字段
#          "output": "JSON",
#      }, timeout=5)
#      data = resp.json()
#      if str(data.get("status")) != "1":
#          raise RuntimeError(f"高德返回错误：{data.get('info')}")
#      places = []
#      for poi in data.get("pois", []):
#          biz = poi.get("biz_ext") or {}
#          places.append({
#              "name":     poi.get("name", ""),
#              "distance": f"{int(poi.get('distance', 0))}m",   # 高德直接返回米数
#              "rating":   biz.get("rating"),                    # 如 4.7
#              "cost":     f"{biz.get('cost')}元",               # 人均，如 "85元"
#              "address":  poi.get("address", ""),
#          })
#      return places
#
#  注：项目内已有完整封装 services/search/amap.py（含错误处理与字段清洗），
#      上线时直接 `from services.search.amap import search as get_real_places` 即可。
# ============================================================