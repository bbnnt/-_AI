/**
 * 知途 · AI 出行与消费性价比决策 Agent（静态演示版核心引擎）
 * 从 routes.py / services/search/base.py / services/geo.py 移植：
 *   Place 模型 / 预算解析 / 关键词提取 / 性价比打分 / CoT三段式Markdown / 定位归一化
 *
 * 静态版链路简化为：我的消费记录(localStorage) → Mock数据兜底 → 规则引擎输出
 * 返回结构与 Flask 版 /api/agent/recommend 完全一致，前端无需改动消费逻辑。
 */
(function (global) {
  'use strict';

  var DEFAULT_BUDGET = 100;
  var SEARCH_LIMIT = 5;

  // ============================================================
  //  Place 统一数据模型（与 services/search/base.py 对齐）
  // ============================================================
  function Place(opts) {
    this.name = opts.name || '';
    this.address = opts.address || '';
    this.rating = opts.rating || null;
    this.avg_cost = opts.avg_cost || null;
    this.distance_m = (opts.distance_m !== undefined && opts.distance_m !== null) ? opts.distance_m : null;
    this.category = opts.category || '';
    this.tags = opts.tags || [];
    this.url = opts.url || '';
    this.snippet = opts.snippet || '';
    this.source = opts.source || '';
  }

  Place.prototype.toDict = function () {
    return {
      name: this.name,
      address: this.address,
      rating: this.rating,
      avg_cost: this.avg_cost,
      distance_m: this.distance_m,
      category: this.category,
      tags: this.tags,
      url: this.url,
      snippet: this.snippet,
      source: this.source,
      distance_text: formatDistance(this.distance_m),
      cost_text: this.avg_cost ? this.avg_cost.toFixed(0) + '元/人' : '未标注',
      rating_text: this.rating ? this.rating.toFixed(1) + '分' : '未标注',
    };
  };

  function formatDistance(meters) {
    if (meters === null || meters === undefined) return '未知';
    if (meters < 1000) return parseInt(meters, 10) + 'm';
    return (meters / 1000).toFixed(1) + 'km';
  }

  function parseDistance(text) {
    if (!text) return null;
    var match = /(\d+(?:\.\d+)?)\s*(公里|千米|km|KM|米|m)/.exec(String(text));
    if (!match) return null;
    var value = parseFloat(match[1]);
    if (isNaN(value)) return null;
    var unit = match[2].toLowerCase();
    var meters = (unit === '公里' || unit === '千米' || unit === 'km') ? value * 1000 : value;
    return parseInt(meters, 10);
  }

  function extractNum(text) {
    var match = /(\d+(?:\.\d+)?)/.exec(String(text || ''));
    return match ? parseFloat(match[1]) : null;
  }

  // Mock 字典 → Place 列表（与 routes._mock_to_places 对齐）
  function mockToPlaces(rawItems) {
    var places = [];
    for (var i = 0; i < rawItems.length; i++) {
      var item = rawItems[i];
      var name = (item.name || '').trim();
      if (!name) continue;
      var rating = item.rating || null;
      var cost = extractNum(item.cost);
      var distText = String(item.distance || '');
      var distanceM = parseDistance(distText);
      var snippet = '店名：' + name + '，距离：' + distText +
        '，评分：' + (rating ? rating : '未获取到') +
        '，人均：' + (cost ? cost.toFixed(0) + '元' : '未获取到');
      places.push(new Place({
        name: name,
        address: (item.address || '').trim(),
        rating: rating,
        avg_cost: cost,
        distance_m: distanceM,
        category: (item.category || '').trim(),
        tags: item.tags || [],
        url: '',
        snippet: snippet,
        source: '离线演示数据（Mock）',
      }));
    }
    return places;
  }

  // ============================================================
  //  预算解析（与 routes.parse_budget 对齐）
  // ============================================================
  var RE_BUDGET_ARABIC = /(\d{2,5})\s*(?:元|块|rmb|RMB|块钱)/;
  var RE_BUDGET_AFTER = /预算[^\d]{0,4}(\d{2,5})/;
  var RE_BUDGET_PER = /人均[^\d]{0,4}(\d{2,5})/;
  var RE_BUDGET_BARE = /(\d{2,5})\s*(?:以内|以下|左右)/;
  var RE_BUDGET_CN = /(?:预算)?([一二两三四五六七八九]?[十百千万]?[一二两三四五六七八九]?[十百]?)\s*(?:元|块)\s*(?:以内|以下|左右)?/;
  var CN_NUM = { '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9 };

  function cnToNumber(text) {
    if (!text) return null;
    var wanIdx = text.indexOf('万');
    if (wanIdx !== -1) {
      var head = text.substring(0, wanIdx);
      var tail = text.substring(wanIdx + 1);
      var base = cnToNumber(head) || 1;
      return base * 10000 + (cnToNumber(tail) || 0);
    }
    var total = 0, section = 0, number = 0;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (ch in CN_NUM) {
        number = CN_NUM[ch];
      } else if (ch === '十') {
        section += (number || 1) * 10;
        number = 0;
      } else if (ch === '百') {
        section += (number || 1) * 100;
        number = 0;
      } else if (ch === '千') {
        section += (number || 1) * 1000;
        number = 0;
      }
    }
    total += section + number;
    return total ? total : null;
  }

  function parseBudget(query) {
    var text = query || '';
    var regexes = [RE_BUDGET_ARABIC, RE_BUDGET_AFTER, RE_BUDGET_PER, RE_BUDGET_BARE];
    for (var i = 0; i < regexes.length; i++) {
      var match = regexes[i].exec(text);
      if (match) {
        var value = parseFloat(match[1]);
        if (value && 5 <= value && value <= 100000) return value;
      }
    }
    var cnMatch = RE_BUDGET_CN.exec(text);
    if (cnMatch) {
      var cnValue = cnToNumber(cnMatch[1]);
      if (cnValue && 5 <= cnValue && cnValue <= 100000) return cnValue;
    }
    return DEFAULT_BUDGET;
  }

  // ============================================================
  //  关键词提取（与 routes.extract_keywords 对齐）
  // ============================================================
  var NOISE_WORDS = [
    '帮我', '请帮我', '麻烦', '我想', '我要', '想要', '一下', '推荐一下',
    '推荐', '附近', '周边', '周围', '性价比', '性价比高', '好吃', '好吃的',
    '的', '找', '来个', '整点', '有没有', '什么', '比较', '好点', '餐厅',
    '预算', '以内', '左右', '元', '块',
    '周末', '周六', '周日', '今天', '明天', '今晚', '中午', '晚上', '夜里',
    '下午', '早上', '想去', '想', '去', '吃顿', '顿', '吃点', '喝点',
  ];
  var EATING_HINTS = ['吃', '餐', '饭', '喝', '味', '食', '馋'];
  var CATEGORY_KEYWORDS = [
    '川菜', '火锅', '烧烤', '串串', '冒菜', '小吃', '面馆', '快餐', '简餐', '日料',
    '寿司', '西餐', '牛排', '披萨', '韩餐', '东北菜', '湘菜', '粤菜', '江浙菜',
    '云南菜', '新疆菜', '清真', '素食', '早茶', '夜宵', '咖啡', '奶茶', '甜品',
    '蛋糕', '面包', '茶餐厅', '自助餐', '砂锅', '米线', '螺蛳粉', '饺子', '包子',
    '东北', '铁锅炖', '锅包肉', '辣椒炒肉', '剁椒', '烧腊', '部队锅', '炸鸡',
    '螺蛳', '担担面', '烤鱼', '烤肉', '串串香', '钵钵鸡',
  ];

  function extractKeywords(query) {
    var text = query || '';
    var hits = [];
    for (var i = 0; i < CATEGORY_KEYWORDS.length; i++) {
      if (text.indexOf(CATEGORY_KEYWORDS[i]) !== -1) hits.push(CATEGORY_KEYWORDS[i]);
    }
    if (hits.length) return hits.slice(0, 2).join(' ');

    for (var j = 0; j < EATING_HINTS.length; j++) {
      if (text.indexOf(EATING_HINTS[j]) !== -1) return '美食';
    }

    var cleaned = text.replace(/\d+\s*(?:元|块|rmb|RMB|块钱)/g, '');
    cleaned = cleaned.replace(/\d{2,5}/g, '');
    for (var k = 0; k < NOISE_WORDS.length; k++) {
      cleaned = cleaned.split(NOISE_WORDS[k]).join('');
    }
    cleaned = cleaned.replace(/[，。！？、,.!?；;:：\s]+/g, ' ').trim();
    return cleaned.length >= 2 ? cleaned : (query || '').trim();
  }

  function buildSearchQuery(query, address) {
    var core = extractKeywords(query);
    var prefix = address || '';
    prefix = prefix.split(',').slice(0, 2).join(' ').trim();
    var parts = [];
    if (prefix) parts.push(prefix);
    if (core) parts.push(core);
    parts.push('人均 评分 推荐');
    return parts.join(' ').trim();
  }

  // ============================================================
  //  性价比打分（与 routes._score_place 对齐：评分50 + 价格35 + 距离15）
  // ============================================================
  function scorePlace(place, budget) {
    if (place.avg_cost && place.avg_cost > budget) return null; // 超预算直接剔除

    var ratingPart = place.rating ? (place.rating / 5.0) * 50 : 40.0;

    var pricePart;
    if (place.avg_cost) {
      var ratio = Math.min(place.avg_cost / budget, 1.0);
      pricePart = 35 * (1 - ratio * 0.5);
    } else {
      pricePart = 20.0;
    }

    var distancePart;
    if (place.distance_m === null || place.distance_m === undefined) {
      distancePart = 8.0;
    } else {
      var km = place.distance_m / 1000.0;
      distancePart = km <= 1 ? 15.0 : Math.max(0.0, 15 - (km - 1) * 3);
    }

    var total = ratingPart + pricePart + distancePart;
    return {
      place: place,
      score: Math.round(total * 10) / 10,
      rating_part: Math.round(ratingPart * 10) / 10,
      price_part: Math.round(pricePart * 10) / 10,
      distance_part: Math.round(distancePart * 10) / 10,
    };
  }

  // ============================================================
  //  CoT 三段式 Markdown（与 routes._fallback_markdown 对齐）
  // ============================================================
  function fallbackMarkdown(query, location, places, budget, providerLabel, reason, userProfile) {
    userProfile = userProfile || {};
    var transport = userProfile.transport || '步行/骑行';
    var people = parseInt(userProfile.people, 10) || 2;
    var hasCoupon = !!userProfile.has_coupon;
    var withKids = !!userProfile.with_kids;

    var allScored = [], rejected = [];
    for (var i = 0; i < places.length; i++) {
      var s = scorePlace(places[i], budget);
      if (s) allScored.push(s);
      else if (places[i].avg_cost && places[i].avg_cost > budget) rejected.push(places[i]);
    }
    allScored.sort(function (a, b) { return b.score - a.score; });
    var scored = allScored.slice(0, 5);

    var head = '> ⚙️ 当前未接入大模型（' + reason + '），以下由规则引擎按**同一套性价比口径**计算，' +
      '并模拟了 Agent 思考链。数据来源：' + providerLabel + '。\n';

    if (!scored.length) {
      return head +
        '\n### 🤔 我的思考过程\n' +
        '1. **理解需求**：' + query + '，人均预算 ' + budget.toFixed(0) + ' 元。\n' +
        '2. **剔除不合适选项**：检索到 ' + places.length + ' 家候选，' +
        '其中 ' + rejected.length + ' 家超预算被剔除，剩余 0 家在预算内。\n' +
        '3. **结论**：没有找到符合预算的方案。\n\n' +
        '### 🏆 最终推荐方案\n' +
        '**未获取到**预算内的候选商家。建议把预算提高到 ' + (budget * 1.5).toFixed(0) + ' 元左右，或换个品类试试。\n\n' +
        '### 💰 真实花费预估\n无法计算（无可用候选）。\n';
    }

    // ---- 🤔 思考过程 ----
    var thinkLines = [
      '1. **理解需求**：' + query + '，人均预算 ' + budget.toFixed(0) + ' 元，' + transport + '出行' +
        (withKids ? '，带小孩' : '') + '。',
      '2. **剔除不合适选项**：共检索到 ' + places.length + ' 家候选——',
    ];
    for (var r = 0; r < rejected.length; r++) {
      var rp = rejected[r];
      thinkLines.push('   - ' + rp.name + '：人均 ' + rp.avg_cost.toFixed(0) + ' 元 > 预算 ' + budget.toFixed(0) + ' 元，**超预算剔除**。');
    }
    if (!rejected.length) {
      thinkLines.push('   - 全部 ' + places.length + ' 家均在预算内，无需剔除。');
    }
    thinkLines.push('3. **计算真实花费**：以人均 × ' + people + ' 人 + ' + transport + '费估算。');
    thinkLines.push('4. **排序得出结论**：剩余 ' + allScored.length + ' 家按性价比分排序，' +
      '第一名 ' + scored[0].place.name + '（' + scored[0].score + ' 分）胜出。');

    // ---- 🏆 推荐方案 ----
    var best = scored[0];
    var bestPlace = best.place;
    var recLines = ['**' + bestPlace.name + '**（性价比分 ' + best.score + '）'];
    if (bestPlace.rating) {
      recLines.push('- 评分 ' + bestPlace.rating.toFixed(1) + ' 分，品质得分项 ' + best.rating_part + '/50');
    }
    if (bestPlace.avg_cost) {
      recLines.push('- 人均 ' + bestPlace.avg_cost.toFixed(0) + ' 元，价格得分项 ' + best.price_part + '/35');
    }
    if (bestPlace.distance_m !== null && bestPlace.distance_m !== undefined) {
      recLines.push('- ' + bestPlace.toDict().distance_text + '，距离得分项 ' + best.distance_part + '/15');
    }
    if (withKids) {
      recLines.push('- 适合带小孩前往');
    }
    if (scored.length > 1) {
      var sp = scored[1].place;
      recLines.push('\n备选：**' + sp.name + '**（性价比分 ' + scored[1].score + '），人均 ' +
        (sp.avg_cost ? sp.avg_cost.toFixed(0) + '元' : '未获取到') + '，' +
        '评分 ' + (sp.rating ? sp.rating.toFixed(1) : '未获取到') + '。');
    }

    // ---- 💰 花费预估 ----
    var cost = bestPlace.avg_cost || budget;
    var foodTotal = cost * people;
    var trafficFee;
    if (transport.indexOf('打车') !== -1) trafficFee = 15;
    else if (transport.indexOf('地铁') !== -1 || transport.indexOf('公交') !== -1) trafficFee = 4;
    else trafficFee = 0;
    var coupon = (hasCoupon && foodTotal >= 200) ? 20 : (hasCoupon ? 10 : 0);
    var realTotal = foodTotal + trafficFee - coupon;
    var distText = (bestPlace.distance_m !== null && bestPlace.distance_m !== undefined) ? bestPlace.toDict().distance_text : '未知';
    var costLines = [
      '> 真实花费 = 人均 × 人数 + 交通费 - 优惠',
      '',
      '- 人均 ' + cost.toFixed(0) + ' 元 × ' + people + ' 人 = ' + foodTotal.toFixed(0) + ' 元',
      '- ' + transport + '费约 ' + trafficFee + ' 元（距离 ' + distText + ' 估算）',
      '- 优惠券抵扣：' + (coupon ? '-' + coupon + ' 元' : '无'),
      '- **真实花费 ≈ ' + realTotal.toFixed(0) + ' 元**',
    ];

    return head +
      '\n### 🤔 我的思考过程\n' + thinkLines.join('\n') + '\n\n' +
      '### 🏆 最终推荐方案\n' + recLines.join('\n') + '\n\n' +
      '### 💰 真实花费预估\n' + costLines.join('\n') + '\n';
  }

  // ============================================================
  //  定位归一化（简化版：本地城市坐标库，与 services/geo.py 对齐）
  //  静态版无后端，跳过高德/OSM联网逆地理，用内置城市库找最近城市。
  // ============================================================
  var LOCAL_CITIES = [
    [39.9042, 116.4074, '北京市'], [31.2304, 121.4737, '上海市'],
    [23.1291, 113.2644, '广州市'], [22.5431, 114.0579, '深圳市'],
    [30.5728, 104.0668, '成都市'], [29.5630, 106.5516, '重庆市'],
    [30.2741, 120.1551, '杭州市'], [30.5928, 114.3055, '武汉市'],
    [34.3416, 108.9398, '西安市'], [32.0603, 118.7969, '南京市'],
    [39.3434, 117.3616, '天津市'], [31.2989, 120.5853, '苏州市'],
    [28.2282, 112.9388, '长沙市'], [34.7466, 113.6254, '郑州市'],
    [36.0671, 120.3826, '青岛市'], [41.8057, 123.4315, '沈阳市'],
    [38.9140, 121.6147, '大连市'], [45.8038, 126.5349, '哈尔滨市'],
    [43.8171, 125.3235, '长春市'], [36.6512, 117.1201, '济南市'],
    [31.8206, 117.2272, '合肥市'], [26.0745, 119.2965, '福州市'],
    [24.4798, 118.0894, '厦门市'], [24.8801, 102.8329, '昆明市'],
    [26.6470, 106.6302, '贵阳市'], [22.8170, 108.3669, '南宁市'],
    [36.0611, 103.8343, '兰州市'], [43.8256, 87.6168, '乌鲁木齐市'],
    [37.8706, 112.5489, '太原市'], [38.0428, 114.5149, '石家庄市'],
    [28.6820, 115.8579, '南昌市'], [29.8683, 121.5440, '宁波市'],
    [23.0218, 113.1219, '佛山市'], [23.0207, 113.7518, '东莞市'],
  ];

  function nearestCity(lat, lng, maxKm) {
    maxKm = maxKm || 80.0;
    var best = null, bestD = maxKm;
    var cosLat = Math.cos(lat * Math.PI / 180);
    for (var i = 0; i < LOCAL_CITIES.length; i++) {
      var c = LOCAL_CITIES[i];
      var d = Math.sqrt(Math.pow((lat - c[0]) * 111.0, 2) + Math.pow((lng - c[1]) * 111.0 * cosLat, 2));
      if (d < bestD) { best = c[2]; bestD = d; }
    }
    return best;
  }

  function resolveLocation(lat, lng, address) {
    if (lat !== null && lat !== undefined && lng !== null && lng !== undefined) {
      if (address && address.length >= 3) {
        return { lat: lat, lng: lng, address: address, source: '手动输入' };
      }
      var city = nearestCity(lat, lng);
      if (city) {
        return { lat: lat, lng: lng, address: city + '（附近）', source: '本地城市库' };
      }
      return { lat: lat, lng: lng, address: lat.toFixed(5) + ',' + lng.toFixed(5), source: '坐标' };
    }
    return { lat: null, lng: null, address: address, source: '手动输入' };
  }

  // ============================================================
  //  主入口：recommend（与 Flask /api/agent/recommend 返回结构一致）
  // ============================================================
  function recommend(opts) {
    var started = Date.now();
    var query = (opts.query || '').trim();
    if (!query) {
      return { ok: false, error: '请先输入你的需求，例如：附近性价比高的川菜' };
    }

    var lat = opts.lat !== undefined && opts.lat !== null && opts.lat !== '' ? parseFloat(opts.lat) : null;
    var lng = opts.lng !== undefined && opts.lng !== null && opts.lng !== '' ? parseFloat(opts.lng) : null;
    var address = (opts.address || '').trim();
    var userProfile = opts.user_profile || {};

    if ((lat === null || lng === null || isNaN(lat) || isNaN(lng)) && !address) {
      return { ok: false, error: '需要先定位：请点击「获取当前位置」，或在下方手动输入地点（如：成都市武侯区）' };
    }

    // ① 定位归一化 + 预算解析
    var location = resolveLocation(lat, lng, address);
    var budget = parseBudget(query);

    // ② 组装搜索词 + 关键词
    var searchQuery = buildSearchQuery(query, location.address || '');
    var keyword = extractKeywords(query) || query;

    // ③ 获取候选商家 —— 静态版链路：我的消费记录 → Mock 兜底
    var places = [];
    var searchSources = [];

    // 第零优先：我的消费记录（localStorage 亲测数据）
    if (global.RecordsStore) {
      var userHits = global.RecordsStore.searchRecords(keyword, location.address || '', SEARCH_LIMIT);
      if (userHits && userHits.length) {
        for (var u = 0; u < userHits.length; u++) {
          places.push(global.RecordsStore.recordToPlace(userHits[u]));
        }
        searchSources.push('我的消费记录');
      }
    }

    // Mock 兜底（补充/兜底，与 Flask 版逻辑一致）
    if (places.length < SEARCH_LIMIT) {
      var rawPlaces = global.MockData.getMockPlaces(location.address || '', keyword, SEARCH_LIMIT);
      var mockPlaces = mockToPlaces(rawPlaces);
      if (places.length) {
        var existingNames = {};
        for (var e = 0; e < places.length; e++) existingNames[places[e].name] = true;
        for (var m = 0; m < mockPlaces.length; m++) {
          if (!existingNames[mockPlaces[m].name] && places.length < SEARCH_LIMIT) {
            places.push(mockPlaces[m]);
          }
        }
      } else {
        places = mockPlaces;
      }
      searchSources.push('离线数据');
    }

    var providerLabel = searchSources.length ? searchSources.join(' + ') : '离线演示数据（Mock·随机采样）';

    // ④ 规则引擎输出（静态版无大模型，始终走规则兜底，保证永远有结果）
    var fallbackReason = '静态演示版，规则引擎内置性价比口径';
    var answer = fallbackMarkdown(query, location, places, budget, providerLabel, fallbackReason, userProfile);

    var placeDicts = [];
    for (var p = 0; p < places.length; p++) placeDicts.push(places[p].toDict());

    return {
      ok: true,
      answer: answer,
      places: placeDicts,
      location: location,
      budget: budget,
      meta: {
        llm: '规则引擎（静态版）',
        search_provider: providerLabel,
        search_query: searchQuery,
        search_errors: [],
        search_notes: [],
        llm_enabled: false,
        web_search_enabled: false,
        fallback: true,
        fallback_reason: fallbackReason,
        elapsed_ms: Date.now() - started,
      },
    };
  }

  global.Agent = {
    Place: Place,
    parseBudget: parseBudget,
    extractKeywords: extractKeywords,
    buildSearchQuery: buildSearchQuery,
    scorePlace: scorePlace,
    fallbackMarkdown: fallbackMarkdown,
    resolveLocation: resolveLocation,
    recommend: recommend,
    DEFAULT_BUDGET: DEFAULT_BUDGET,
  };
})(window);