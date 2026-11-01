/**
 * 知途 · 前端交互（智能体化版）
 * 1) H5 定位（顶栏压缩入口，失败可手输兜底）
 * 2) 聊天式多轮对话：维护 chat_history，支持追问
 * 3) Markdown 渲染：优先 marked.js（CDN），加载失败用自研轻量渲染兜底
 * 4) 个性化参数：勾选框 → user_profile 随请求传后端
 * 5) 执行闭环：AI 气泡旁【📥 导出比价报告】→ window.print()
 */
(function () {
  'use strict';

  var state = {
    lat: null,
    lng: null,
    address: '',
    loading: false,
    chatHistory: []    // [{role:'user'|'assistant', content:'...'}]
  };

  function $(id) { return document.getElementById(id); }

  /* ============================================================
   *  基础工具
   * ============================================================ */
  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  var toastTimer = null;
  function toast(message) {
    var el = $('toast');
    el.textContent = message;
    el.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.add('hidden'); }, 3200);
  }

  function scrollToBottom() {
    var box = $('chatBox');
    box.scrollTop = box.scrollHeight;
  }

  /* ============================================================
   *  Markdown 渲染
   *  优先 marked.js（CDN），不可用时降级到自研轻量渲染
   * ============================================================ */
  function mdRender(markdown) {
    if (!markdown) return '';
    if (typeof marked !== 'undefined' && marked.parse) {
      try { return marked.parse(markdown, { breaks: true }); }
      catch (e) { /* 降级 */ }
    }
    return lightRender(markdown);
  }

  /* ---- 自研轻量渲染（断网兜底，支持标题/表格/列表/加粗/引用） ---- */
  function renderInline(text) {
    var t = escapeHtml(text);
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    return t;
  }
  function splitCells(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (c) { return c.trim(); });
  }
  function isTableRow(line) { return line.indexOf('|') !== -1 && splitCells(line).length >= 2; }
  function isTableSep(line) { return /^\|?[\s:|-]*-[\s:|-]*\|?$/.test(line.trim()) && line.indexOf('|') !== -1; }

  function lightRender(markdown) {
    var lines = String(markdown).split(/\r?\n/);
    var out = [], i = 0, listTag = null, para = [];
    function flushPara() { if (para.length) { out.push('<p>' + renderInline(para.join(' ')) + '</p>'); para = []; } }
    function closeList() { if (listTag) { out.push('</' + listTag + '>'); listTag = null; } }
    while (i < lines.length) {
      var line = lines[i].trim();
      if (!line) { flushPara(); closeList(); i++; continue; }
      if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        flushPara(); closeList();
        var header = splitCells(line), j = i + 2, rows = [];
        while (j < lines.length && isTableRow(lines[j].trim())) { rows.push(splitCells(lines[j].trim())); j++; }
        out.push('<div class="md-table-wrap"><table class="md-table"><thead><tr>' +
          header.map(function (h) { return '<th>' + renderInline(h) + '</th>'; }).join('') +
          '</tr></thead><tbody>' + rows.map(function (r) {
            return '<tr>' + r.map(function (c) { return '<td>' + renderInline(c) + '</td>'; }).join('') + '</tr>';
          }).join('') + '</tbody></table></div>');
        i = j; continue;
      }
      var hm = line.match(/^(#{1,6})\s+(.*)$/);
      if (hm) { flushPara(); closeList(); var lv = Math.min(hm[1].length + 1, 6); out.push('<h' + lv + '>' + renderInline(hm[2]) + '</h' + lv + '>'); i++; continue; }
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) { flushPara(); closeList(); out.push('<hr>'); i++; continue; }
      if (/^>\s?/.test(line)) {
        flushPara(); closeList(); var q = [];
        while (i < lines.length && /^>\s?/.test(lines[i].trim())) { q.push(lines[i].trim().replace(/^>\s?/, '')); i++; }
        out.push('<blockquote>' + renderInline(q.join(' ')) + '</blockquote>'); continue;
      }
      var ul = line.match(/^[-*+]\s+(.*)$/);
      if (ul) { flushPara(); if (listTag !== 'ul') { closeList(); out.push('<ul>'); listTag = 'ul'; } out.push('<li>' + renderInline(ul[1]) + '</li>'); i++; continue; }
      var ol = line.match(/^\d+[.)]\s+(.*)$/);
      if (ol) { flushPara(); if (listTag !== 'ol') { closeList(); out.push('<ol>'); listTag = 'ol'; } out.push('<li>' + renderInline(ol[1]) + '</li>'); i++; continue; }
      closeList(); para.push(line); i++;
    }
    flushPara(); closeList();
    return out.join('\n');
  }

  /* ============================================================
   *  定位
   * ============================================================ */
  function setLocBadge(text, kind) {
    var badge = $('locBadge');
    badge.textContent = text;
    badge.className = 'loc-badge' + (kind ? ' ' + kind : '');
  }

  function isSecureContext() {
    return window.isSecureContext === true ||
      location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  }

  function locate() {
    if (!navigator.geolocation) { setLocBadge('不支持定位', 'warn'); return; }
    if (!isSecureContext()) { setLocBadge('需 HTTPS', 'warn'); return; }
    setLocBadge('定位中…', 'loading');
    navigator.geolocation.getCurrentPosition(function (pos) {
      state.lat = Number(pos.coords.latitude.toFixed(6));
      state.lng = Number(pos.coords.longitude.toFixed(6));
      state.address = '';
      setLocBadge('已定位', 'ok');
    }, function (err) {
      setLocBadge('定位失败', 'warn');
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
  }

  function useManualAddress() {
    var address = $('addressInput').value.trim();
    if (!address) { toast('请先输入地点'); return; }
    state.address = address;
    state.lat = null; state.lng = null;
    setLocBadge('已手输', 'ok');
  }

  /* ============================================================
   *  聊天气泡
   * ============================================================ */
  function addUserMsg(text) {
    var box = $('chatBox');
    var el = document.createElement('div');
    el.className = 'msg user-msg';
    el.innerHTML = '<div class="bubble"><div class="bubble-content">' + escapeHtml(text) + '</div></div>';
    box.appendChild(el);
    scrollToBottom();
  }

  function addLoadingMsg() {
    var box = $('chatBox');
    var el = document.createElement('div');
    el.className = 'msg ai-msg loading-msg';
    el.id = 'loadingMsg';
    el.innerHTML = '<div class="avatar">🤖</div><div class="bubble"><div class="bubble-content">' +
      '<div class="typing"><span></span><span></span><span></span></div>' +
      '<p class="typing-text">正在检索周边门店并推理算账…</p></div></div>';
    box.appendChild(el);
    scrollToBottom();
  }

  function removeLoadingMsg() {
    var el = $('loadingMsg');
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function addAiMsg(data) {
    var box = $('chatBox');
    var el = document.createElement('div');
    el.className = 'msg ai-msg';

    var metaHtml = '';
    var meta = data.meta || {};
    var chips = [];
    // 模式标识：AI思考/快速模式 + 联网/离线
    if (meta.llm_enabled === false) {
      chips.push('⚡ 快速模式');
    } else if (meta.fallback) {
      chips.push('⚠️ 规则兜底');
    } else {
      chips.push('🧠 AI 深度思考');
    }
    if (meta.web_search_enabled === false) {
      chips.push('📦 离线数据');
    } else if (meta.search_provider) {
      chips.push('🌐 ' + escapeHtml(meta.search_provider));
    }
    if (meta.elapsed_ms) chips.push('⏱ ' + (meta.elapsed_ms / 1000).toFixed(1) + 's');
    if (chips.length) metaHtml = '<div class="msg-meta">' + chips.map(function (c) { return '<span class="meta-chip">' + c + '</span>'; }).join('') + '</div>';

    el.innerHTML = '<div class="avatar">🤖</div><div class="bubble">' +
      '<div class="bubble-content markdown">' + mdRender(data.answer || '') + '</div>' +
      metaHtml +
      '<div class="msg-actions no-print"><button class="btn ghost sm export-btn">📥 导出比价报告</button></div>' +
      '</div>';
    box.appendChild(el);

    // 导出按钮
    el.querySelector('.export-btn').addEventListener('click', function () { window.print(); });

    scrollToBottom();
  }

  function addErrorMsg(message) {
    var box = $('chatBox');
    var el = document.createElement('div');
    el.className = 'msg ai-msg';
    el.innerHTML = '<div class="avatar">🤖</div><div class="bubble"><div class="bubble-content">' +
      '<p class="error-text">⚠️ ' + escapeHtml(message) + '</p></div></div>';
    box.appendChild(el);
    scrollToBottom();
  }

  /* ============================================================
   *  个性化参数收集
   * ============================================================ */
  function collectProfile(query) {
    var transportEl = document.querySelector('input[name="transport"]:checked');
    return {
      budget: null,              // 预算从 query 自然语言提取，后端 parse_budget 处理
      people: parseInt($('numPeople').value, 10) || 2,
      with_kids: $('chkKids').checked,
      has_coupon: $('chkCoupon').checked,
      transport: transportEl ? transportEl.value : '打车'
    };
  }

  /* ============================================================
   *  发送（多轮对话）
   * ============================================================ */
  function generate() {
    var query = $('queryInput').value.trim();
    if (!query) { toast('请先描述你的需求'); $('queryInput').focus(); return; }
    if (state.lat == null && !state.address && !$('addressInput').value.trim()) {
      toast('请先点击「📍 定位」，或手输地点'); return;
    }

    // 渲染用户气泡 & 记录历史
    addUserMsg(query);
    state.chatHistory.push({ role: 'user', content: query });
    $('queryInput').value = '';

    var profile = collectProfile(query);
    var payload = {
      query: query,
      lat: state.lat,
      lng: state.lng,
      address: state.address || $('addressInput').value.trim(),
      chat_history: state.chatHistory.slice(0, -1),   // 之前的历史（不含刚发的这条）
      user_profile: profile,
      llm_enabled: $('toggleLLM').checked,            // AI深度思考开关
      web_search_enabled: $('toggleWebSearch').checked, // 联网搜索开关
    };

    state.loading = true;
    $('btnGenerate').disabled = true;
    $('btnGenerate').textContent = '思考中…';
    addLoadingMsg();

    fetch('/api/agent/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || ('请求失败，HTTP ' + res.status));
          return data;
        });
      })
      .then(function (data) {
        removeLoadingMsg();
        // 定位回填
        var loc = data.location || {};
        if (loc.address) {
          state.address = loc.address;
          setLocBadge(loc.address.split(/[（(]/)[0], 'ok');
        }
        addAiMsg(data);
        // 记录 AI 回复到历史（截断防Token爆炸）
        state.chatHistory.push({ role: 'assistant', content: (data.answer || '').slice(0, 500) });
      })
      .catch(function (err) {
        removeLoadingMsg();
        addErrorMsg(err.message || '生成失败，请稍后重试');
      })
      .then(function () {
        state.loading = false;
        $('btnGenerate').disabled = false;
        $('btnGenerate').textContent = '发送';
      });
  }

  /* ============================================================
   *  事件绑定
   * ============================================================ */
  function bind() {
    $('btnLocate').addEventListener('click', locate);
    $('btnUseAddress').addEventListener('click', useManualAddress);
    $('btnGenerate').addEventListener('click', generate);

    $('addressInput').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') useManualAddress();
    });
    $('queryInput').addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') generate();
    });

    // 快捷 chips：填入输入框并发送
    var chips = document.querySelectorAll('.chip[data-sample]');
    Array.prototype.forEach.call(chips, function (chip) {
      chip.addEventListener('click', function () {
        $('queryInput').value = chip.getAttribute('data-sample');
        generate();
      });
    });

    // textarea 自适应高度
    $('queryInput').addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    bind();
    setTimeout(locate, 600);
  });
})();