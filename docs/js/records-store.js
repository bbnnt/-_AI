/**
 * 知途 · 用户消费记录库（静态演示版）
 * 从 user_db.py 移植：JSON 文件持久化 → localStorage 持久化
 * 接口与 Flask 版 /api/records 完全对齐：list / add / delete / search / recordToPlace
 */
(function (global) {
  'use strict';

  var STORAGE_KEY = 'zhitu_user_records';

  // 评价里的数字评分识别：纯数字或 X.X 分
  var RE_RATING_TEXT = /^([0-5](?:\.\d)?)\s*分?$/;

  function parseRating(comment) {
    if (!comment) return null;
    var match = RE_RATING_TEXT.exec(comment.trim());
    if (!match) return null;
    var value = parseFloat(match[1]);
    return (value >= 0 && value <= 5) ? value : null;
  }

  function loadAll() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      var data = JSON.parse(raw);
      return Array.isArray(data) ? data : [];
    } catch (e) {
      return [];
    }
  }

  function saveAll(records) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
    } catch (e) {
      // localStorage 满或隐私模式：静默降级，本次会话内存态仍可用
      console.warn('[RecordsStore] localStorage 写入失败:', e);
    }
  }

  function genId() {
    return 'r' + Date.now().toString(36) + Math.random().toString(36).substring(2, 8);
  }

  // ============================================================
  //  CRUD
  // ============================================================
  function addRecord(opts) {
    var name = (opts.name || '').trim();
    if (!name) throw new Error('饭店名称不能为空');

    var people = opts.people ? parseInt(opts.people, 10) : null;
    var avgCost = opts.avg_cost ? parseFloat(opts.avg_cost) : null;
    var totalCost = opts.total_cost ? parseFloat(opts.total_cost) : null;

    var record = {
      id: genId(),
      name: name,
      address: (opts.address || '').trim(),
      people: people && !isNaN(people) ? people : null,
      avg_cost: avgCost && !isNaN(avgCost) ? avgCost : null,
      total_cost: totalCost && !isNaN(totalCost) ? totalCost : null,
      comment: (opts.comment || '').trim(),
      created_at: Math.floor(Date.now() / 1000),
    };
    var records = loadAll();
    records.push(record);
    saveAll(records);
    return record;
  }

  function listRecords() {
    var records = loadAll();
    records.sort(function (a, b) { return (b.created_at || 0) - (a.created_at || 0); });
    return records;
  }

  function deleteRecord(recordId) {
    var records = loadAll();
    var remaining = records.filter(function (r) { return r.id !== recordId; });
    if (remaining.length === records.length) return false;
    saveAll(remaining);
    return true;
  }

  // ============================================================
  //  搜索匹配 + 转 Place 模型（与 user_db.py 对齐）
  // ============================================================
  function recordText(record) {
    return [record.name || '', record.address || '', record.comment || '']
      .filter(Boolean).join(' ');
  }

  function searchRecords(keyword, address, limit) {
    limit = limit || 5;
    var records = loadAll();
    if (!records.length) return [];

    // 分词：中文按 2 字滑窗 + 直接切出品类词
    var words = {};
    var text = keyword || '';
    var tokens = text.match(/[\u4e00-\u9fa5]{2,}|[a-zA-Z]+/g) || [];
    for (var t = 0; t < tokens.length; t++) words[tokens[t]] = true;
    for (var ch = 0; ch < text.length; ch++) {
      var c = text[ch];
      if (/[\u4e00-\u9fa5]/.test(c)) words[c] = true;
    }
    delete words[''];
    var wordList = Object.keys(words);
    if (!wordList.length) return [];

    var scored = [];
    for (var i = 0; i < records.length; i++) {
      var record = records[i];
      var hay = recordText(record);
      var hits = 0;
      for (var w = 0; w < wordList.length; w++) {
        if (hay.indexOf(wordList[w]) !== -1) hits++;
      }
      if (hits <= 0) continue;
      // 地址同城加分
      var recAddr = record.address || '';
      var addrBonus = 0;
      if (address && recAddr) {
        var segs = address.split(/\s+/);
        for (var s = 0; s < segs.length; s++) {
          if (segs[s].length >= 2 && recAddr.indexOf(segs[s]) !== -1) { addrBonus = 1; break; }
        }
      }
      scored.push({ score: hits + addrBonus, created: record.created_at || 0, record: record });
    }

    scored.sort(function (a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return b.created - a.created;
    });
    return scored.slice(0, limit).map(function (item) { return item.record; });
  }

  function recordToPlace(record) {
    var name = (record.name || '').trim();
    var address = (record.address || '').trim();
    var avgCost = record.avg_cost ? parseFloat(record.avg_cost) : null;
    var comment = (record.comment || '').trim();
    var rating = parseRating(comment);

    // 组装"真实依据"摘要
    var parts = ['店名：' + name];
    if (address) parts.push('地址：' + address);
    if (record.people) parts.push('本次消费人数：' + record.people + ' 人');
    if (avgCost) parts.push('人均：' + avgCost.toFixed(0) + ' 元');
    if (record.total_cost) parts.push('总价：' + parseFloat(record.total_cost).toFixed(0) + ' 元');
    if (comment) parts.push('我的评价：' + comment);
    var snippet = parts.join('，');

    var tags = [];
    if (comment && !rating) tags.push(comment.substring(0, 12));
    tags.push('本人消费过');

    return new global.Agent.Place({
      name: name,
      address: address,
      rating: rating,
      avg_cost: avgCost,
      distance_m: null,
      category: '',
      tags: tags,
      url: '',
      snippet: snippet,
      source: '我的消费记录',
    });
  }

  global.RecordsStore = {
    addRecord: addRecord,
    listRecords: listRecords,
    deleteRecord: deleteRecord,
    searchRecords: searchRecords,
    recordToPlace: recordToPlace,
  };
})(window);