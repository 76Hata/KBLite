/* ============================================================
 * observability.js — Observability ダッシュボード
 * Claude Code のツール使用状況 + LLM使用量を可視化する
 * ============================================================ */

/* global showToast */

// ── 状態 ──────────────────────────────────────────────────────
let _obsData = null;
let _llmData = null;
let _obsDays = 1;
let _obsTab = "tools"; // "tools" | "llm"
let _obsFrom = "";     // カスタム期間: 開始日 (YYYY-MM-DD)
let _obsTo = "";       // カスタム期間: 終了日 (YYYY-MM-DD)
let _llmRecentPage = 1;
let _llmRecentSize = 20;
let _evtRecentPage = 1;
let _evtRecentSize = 20;

// ── 表示切替 ──────────────────────────────────────────────────
function openObservability() {
  const view = document.getElementById("observabilityView");
  if (view.style.display !== "none") {
    closeObservability();
    return;
  }
  // 初期表示時のみ、_obsDays に基づいて日付範囲の初期値を設定する
  if (!_obsFrom && !_obsTo) {
    const today = new Date();
    _obsTo = _formatDate(today);
    const from = new Date(today);
    from.setDate(today.getDate() - (_obsDays - 1));
    _obsFrom = _formatDate(from);
  }
  document.getElementById("chatView").style.display = "none";
  document.getElementById("logView").style.display = "none";
  view.style.display = "block";
  loadObservabilityData();
}

function closeObservability() {
  document.getElementById("observabilityView").style.display = "none";
  document.getElementById("chatView").style.display = "flex";
}

// ── データ取得 ────────────────────────────────────────────────
function _buildObsQuery() {
  const params = new URLSearchParams();
  if (_obsFrom || _obsTo) {
    if (_obsFrom) params.set("from", _obsFrom);
    if (_obsTo) params.set("to", _obsTo);
  } else {
    params.set("days", _obsDays);
  }
  return params.toString();
}

async function loadObservabilityData() {
  _llmRecentPage = 1;
  _evtRecentPage = 1;
  const container = document.getElementById("obsContent");
  container.innerHTML = '<div class="obs-loading">読み込み中...</div>';
  try {
    const q = _buildObsQuery();
    const [obsRes, llmRes] = await Promise.all([
      fetch(`/api/observability?${q}`),
      fetch(`/api/llm-usage?${q}`),
    ]);
    if (!obsRes.ok) throw new Error(`Observability HTTP ${obsRes.status}`);
    _obsData = await obsRes.json();
    _llmData = llmRes.ok ? await llmRes.json() : null;
    renderObservability();
  } catch (e) {
    container.innerHTML = `<div class="obs-error">データ取得エラー: ${e.message}</div>`;
  }
}

// ── メインレンダリング ────────────────────────────────────────
function renderObservability() {
  const container = document.getElementById("obsContent");

  // 期間セレクタ + タブ
  const customActive = _obsFrom || _obsTo;
  const periodHtml = `
    <div class="obs-period">
      <div class="obs-tabs">
        <button class="obs-tab ${_obsTab==="tools"?"active":""}" onclick="_obsTab='tools';renderObservability()">ツール使用</button>
        <button class="obs-tab ${_obsTab==="llm"?"active":""}" onclick="_obsTab='llm';renderObservability()">LLM使用量</button>
      </div>
      <label>期間:</label>
      <select onchange="_obsDays=+this.value;_obsFrom='';_obsTo='';loadObservabilityData()" ${customActive?"style='opacity:0.5'":""}>
        <option value="1" ${_obsDays===1&&!customActive?"selected":""}>1日</option>
        <option value="3" ${_obsDays===3&&!customActive?"selected":""}>3日</option>
        <option value="7" ${_obsDays===7&&!customActive?"selected":""}>7日</option>
        <option value="14" ${_obsDays===14&&!customActive?"selected":""}>14日</option>
        <option value="30" ${_obsDays===30&&!customActive?"selected":""}>30日</option>
      </select>
      <span class="obs-date-range">
        <input type="date" value="${_obsFrom}" onchange="_obsFrom=this.value;_applyDateRange()" title="開始日">
        <span class="obs-date-sep">〜</span>
        <input type="date" value="${_obsTo}" onchange="_obsTo=this.value;_applyDateRange()" title="終了日">
      </span>
      ${customActive ? '<button onclick="_resetObsDateRange()" class="obs-reset-btn" title="日付指定を解除">✕</button>' : ''}
      <button onclick="loadObservabilityData()" class="obs-refresh-btn">更新</button>
    </div>`;

  if (_obsTab === "llm") {
    container.innerHTML = periodHtml + _renderLlmTab();
    return;
  }

  // ── ツール使用タブ ──
  const d = _obsData;
  if (!d) return;

  const toolCount = Object.keys(d.tool_counts).length;
  const summaryHtml = `
    <div class="obs-summary">
      <div class="obs-card">
        <div class="obs-card-value">${d.total_events.toLocaleString()}</div>
        <div class="obs-card-label">総イベント数</div>
      </div>
      <div class="obs-card">
        <div class="obs-card-value">${toolCount}</div>
        <div class="obs-card-label">ツール種類</div>
      </div>
      <div class="obs-card">
        <div class="obs-card-value">${d.days}</div>
        <div class="obs-card-label">対象日数</div>
      </div>
      <div class="obs-card">
        <div class="obs-card-value">${_calcPeakHour(d.hourly_distribution)}</div>
        <div class="obs-card-label">ピーク時間帯</div>
      </div>
    </div>`;

  const toolRankHtml = _renderToolRanking(d.tool_counts);
  const eventHtml = _renderEventCounts(d.event_counts);
  const clientHtml = _renderClientCounts(d.client_counts);
  const dailyHtml = _renderDailyChart(d.daily_counts);
  const hourlyHtml = _renderHourlyChart(d.hourly_distribution);
  const recentHtml = _renderRecentEvents(d.recent_events);

  container.innerHTML = periodHtml + summaryHtml
    + '<div class="obs-grid">'
    + '<div class="obs-section">' + toolRankHtml + '</div>'
    + '<div class="obs-section">' + eventHtml + '</div>'
    + '</div>'
    + '<div class="obs-section">' + clientHtml + '</div>'
    + '<div class="obs-section">' + dailyHtml + '</div>'
    + '<div class="obs-section">' + hourlyHtml + '</div>'
    + '<div class="obs-section">' + recentHtml + '</div>';
}

// ── LLM使用量タブ ────────────────────────────────────────────
function _renderLlmTab() {
  const d = _llmData;
  if (!d || d.total_calls === 0) {
    return '<div class="obs-section"><p class="obs-empty">LLM使用量データがありません。KBブラウザからチャットを実行するとデータが記録されます。</p></div>';
  }

  const summaryHtml = `
    <div class="obs-summary">
      <div class="obs-card">
        <div class="obs-card-value">${d.total_calls.toLocaleString()}</div>
        <div class="obs-card-label">総呼び出し回数</div>
      </div>
      <div class="obs-card">
        <div class="obs-card-value">${_formatTokens(d.total_tokens.input)}</div>
        <div class="obs-card-label">入力トークン</div>
      </div>
      <div class="obs-card">
        <div class="obs-card-value">${_formatTokens(d.total_tokens.output)}</div>
        <div class="obs-card-label">出力トークン</div>
      </div>
      <div class="obs-card">
        <div class="obs-card-value">${_formatTokens(d.total_tokens.cache_read)}</div>
        <div class="obs-card-label">キャッシュ読取</div>
      </div>
    </div>`;

  const modelHtml = _renderModelBreakdown(d.by_model);
  const dailyHtml = _renderLlmDailyChart(d.daily);
  const recentHtml = _renderLlmRecent(d.recent);

  return summaryHtml
    + '<div class="obs-section">' + modelHtml + '</div>'
    + '<div class="obs-section">' + dailyHtml + '</div>'
    + '<div class="obs-section">' + recentHtml + '</div>';
}

function _formatTokens(n) {
  if (n == null || n === 0) return "0";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return n.toLocaleString();
}

function _renderModelBreakdown(byModel) {
  const entries = Object.entries(byModel).sort((a, b) => b[1].calls - a[1].calls);
  if (!entries.length) return '<h3>モデル別使用量</h3><p class="obs-empty">データなし</p>';

  const modelColors = {
    "Opus": "#e57373", "Opus 4.5": "#ef5350",
    "Sonnet": "#64b5f6", "Sonnet 3.5": "#42a5f5",
    "Haiku": "#81c784",
  };
  const maxCalls = Math.max(...entries.map(e => e[1].calls));

  const rows = entries.map(([model, stats]) => {
    const color = modelColors[model] || "#aaa";
    const pct = Math.round((stats.calls / maxCalls) * 100);
    const totalTokens = stats.input_tokens + stats.output_tokens;
    return `<div class="obs-bar-row">
      <span class="obs-bar-label" style="min-width:60px">
        <span class="obs-event-dot" style="background:${color}"></span>${_escHtml(model)}
      </span>
      <div class="obs-bar-track"><div class="obs-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <span class="obs-bar-value" style="min-width:140px;text-align:right;font-size:0.82em">
        ${stats.calls}回 / ${_formatTokens(totalTokens)}tk
      </span>
    </div>`;
  }).join("");

  // トークン内訳テーブル
  const detailRows = entries.map(([model, s]) => {
    const color = modelColors[model] || "#aaa";
    return `<tr>
      <td><span class="obs-event-dot" style="background:${color}"></span>${_escHtml(model)}</td>
      <td class="obs-num">${s.calls}</td>
      <td class="obs-num">${_formatTokens(s.input_tokens)}</td>
      <td class="obs-num">${_formatTokens(s.output_tokens)}</td>
      <td class="obs-num">${_formatTokens(s.cache_read_tokens)}</td>
    </tr>`;
  }).join("");

  return `<h3>モデル別使用量</h3>${rows}
    <div class="obs-table-wrap" style="margin-top:12px">
      <table class="obs-table">
        <thead><tr><th>モデル</th><th class="obs-num">回数</th><th class="obs-num">入力</th><th class="obs-num">出力</th><th class="obs-num">Cache読取</th></tr></thead>
        <tbody>${detailRows}</tbody>
      </table>
    </div>`;
}

function _renderLlmDailyChart(daily) {
  const entries = Object.entries(daily).sort();
  if (!entries.length) return '<h3>日別LLM呼び出し</h3><p class="obs-empty">データなし</p>';

  const maxVal = Math.max(...entries.map(e => e[1].calls), 1);
  const bars = entries.map(([day, stats]) => {
    const pct = Math.round((stats.calls / maxVal) * 100);
    const label = day.slice(5);
    const tokens = stats.input_tokens + stats.output_tokens;
    return `<div class="obs-daily-col" title="${day}: ${stats.calls}回 / ${_formatTokens(tokens)}tk">
      <div class="obs-daily-bar-wrap"><div class="obs-daily-bar" style="height:${pct}%;background:#64b5f6"></div></div>
      <div class="obs-daily-label">${label}</div>
      <div class="obs-daily-value">${stats.calls}</div>
    </div>`;
  }).join("");

  return `<h3>日別LLM呼び出し</h3><div class="obs-daily-chart">${bars}</div>`;
}

function _renderLlmRecent(recent) {
  if (!recent || !recent.length) return '<h3>直近のLLM呼び出し</h3><p class="obs-empty">データなし</p>';

  const total = recent.length;
  const totalPages = Math.ceil(total / _llmRecentSize);
  if (_llmRecentPage > totalPages) _llmRecentPage = totalPages;
  const start = (_llmRecentPage - 1) * _llmRecentSize;
  const page = recent.slice(start, start + _llmRecentSize);

  const rows = page.map(r => {
    const ts = (r.created_at || "").replace("T", " ").slice(0, 19);
    const dur = r.duration_ms > 0 ? (r.duration_ms / 1000).toFixed(1) + "s" : "-";
    return `<tr>
      <td class="obs-ts">${_escHtml(ts)}</td>
      <td>${_escHtml(r.model)}</td>
      <td class="obs-num">${_formatTokens(r.input_tokens)}</td>
      <td class="obs-num">${_formatTokens(r.output_tokens)}</td>
      <td class="obs-num">${_formatTokens(r.cache_read_tokens)}</td>
      <td class="obs-num">${r.num_turns}</td>
      <td class="obs-num">${dur}</td>
    </tr>`;
  }).join("");

  return `<h3>直近のLLM呼び出し (${total}件)</h3>
    ${_renderPager("llm", _llmRecentPage, totalPages, _llmRecentSize, total)}
    <div class="obs-table-wrap">
      <table class="obs-table">
        <thead><tr><th>時刻</th><th>モデル</th><th class="obs-num">入力</th><th class="obs-num">出力</th><th class="obs-num">Cache</th><th class="obs-num">ターン</th><th class="obs-num">所要</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${totalPages > 1 ? _renderPager("llm", _llmRecentPage, totalPages, _llmRecentSize, total) : ""}`;
}

// ── ヘルパー ──────────────────────────────────────────────────

function _calcPeakHour(hourly) {
  let maxH = "00", maxV = 0;
  for (const [h, v] of Object.entries(hourly)) {
    if (v > maxV) { maxV = v; maxH = h; }
  }
  return maxV > 0 ? `${parseInt(maxH, 10)}:00` : "-";
}

function _renderToolRanking(counts) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return '<h3>ツール使用ランキング</h3><p class="obs-empty">データなし</p>';

  const maxVal = entries[0][1];
  const rows = entries.slice(0, 15).map(([tool, count]) => {
    const pct = Math.round((count / maxVal) * 100);
    return `<div class="obs-bar-row">
      <span class="obs-bar-label">${_escHtml(tool)}</span>
      <div class="obs-bar-track"><div class="obs-bar-fill" style="width:${pct}%"></div></div>
      <span class="obs-bar-value">${count}</span>
    </div>`;
  }).join("");

  return `<h3>ツール使用ランキング (Top 15)</h3>${rows}`;
}

function _renderEventCounts(counts) {
  const entries = Object.entries(counts);
  if (!entries.length) return '<h3>イベント種別</h3><p class="obs-empty">データなし</p>';

  const colorMap = {
    PreToolUse: "#4fc3f7",
    PostToolUse: "#81c784",
    Stop: "#ffb74d",
    SessionStart: "#ce93d8",
    unknown: "#999",
  };

  const descMap = {
    PreToolUse: "ツール実行前",
    PostToolUse: "ツール実行後",
    Stop: "応答完了",
    SessionStart: "セッション開始",
    UserPromptSubmit: "ユーザー入力",
    SubagentStart: "サブエージェント開始",
    SubagentStop: "サブエージェント終了",
    Notification: "通知",
    PreCompact: "コンテキスト圧縮前",
    PostCompact: "コンテキスト圧縮後",
    unknown: "不明",
  };

  const rows = entries.map(([ev, count]) => {
    const color = colorMap[ev] || "#aaa";
    const desc = descMap[ev] || "";
    return `<div class="obs-event-row">
      <span class="obs-event-dot" style="background:${color}"></span>
      <span class="obs-event-name">${_escHtml(ev)}</span>${desc ? `<span class="obs-event-desc">${_escHtml(desc)}</span>` : ""}
      <span class="obs-event-count">${count}</span>
    </div>`;
  }).join("");

  return `<h3>イベント種別</h3>${rows}`;
}

function _renderClientCounts(counts) {
  const entries = Object.entries(counts || {});
  if (!entries.length) return '<h3>起動元</h3><p class="obs-empty">データなし</p>';

  const colorMap = {
    terminal: "#78909c",
  };

  const rows = entries.sort((a, b) => b[1] - a[1]).map(([client, count]) => {
    const isKB = client.startsWith("KB");
    const color = colorMap[client] || (isKB ? "#42a5f5" : "#aaa");
    return `<div class="obs-event-row">
      <span class="obs-event-dot" style="background:${color}"></span>
      <span class="obs-event-name">${_escHtml(client)}</span>
      <span class="obs-event-count">${count}</span>
    </div>`;
  }).join("");

  return `<h3>起動元</h3>${rows}`;
}

function _renderDailyChart(daily) {
  const entries = Object.entries(daily).sort();
  if (!entries.length) return '<h3>日別アクティビティ</h3><p class="obs-empty">データなし</p>';

  const maxVal = Math.max(...entries.map(e => e[1]), 1);
  const bars = entries.map(([day, count]) => {
    const pct = Math.round((count / maxVal) * 100);
    const label = day.slice(5); // MM-DD
    return `<div class="obs-daily-col">
      <div class="obs-daily-bar-wrap"><div class="obs-daily-bar" style="height:${pct}%"></div></div>
      <div class="obs-daily-label">${label}</div>
      <div class="obs-daily-value">${count}</div>
    </div>`;
  }).join("");

  return `<h3>日別アクティビティ</h3><div class="obs-daily-chart">${bars}</div>`;
}

function _renderHourlyChart(hourly) {
  const entries = Object.entries(hourly).sort();
  if (!entries.length) return '<h3>時間帯分布</h3><p class="obs-empty">データなし</p>';

  const maxVal = Math.max(...entries.map(e => e[1]), 1);
  const bars = entries.map(([hour, count]) => {
    const pct = Math.round((count / maxVal) * 100);
    return `<div class="obs-hourly-col">
      <div class="obs-hourly-bar-wrap"><div class="obs-hourly-bar" style="height:${pct}%"></div></div>
      <div class="obs-hourly-label">${parseInt(hour, 10)}</div>
    </div>`;
  }).join("");

  return `<h3>時間帯分布 (0-23時)</h3><div class="obs-hourly-chart">${bars}</div>`;
}

function _renderRecentEvents(events) {
  if (!events || !events.length) return '<h3>直近イベント</h3><p class="obs-empty">データなし</p>';

  const total = events.length;
  const totalPages = Math.ceil(total / _evtRecentSize);
  if (_evtRecentPage > totalPages) _evtRecentPage = totalPages;
  const start = (_evtRecentPage - 1) * _evtRecentSize;
  const page = events.slice(start, start + _evtRecentSize);

  const rows = page.map(ev => {
    const ts = (ev.ts || "").replace("T", " ").slice(0, 19);
    const tool = ev.tool || "-";
    const event = ev.event || "-";
    const client = ev.client || "-";
    return `<tr>
      <td class="obs-ts">${_escHtml(ts)}</td>
      <td><span class="obs-badge obs-badge-${event.toLowerCase()}">${_escHtml(event)}</span></td>
      <td>${_escHtml(tool)}</td>
      <td>${_escHtml(client)}</td>
    </tr>`;
  }).join("");

  return `<h3>直近イベント (${total}件)</h3>
    ${_renderPager("evt", _evtRecentPage, totalPages, _evtRecentSize, total)}
    <div class="obs-table-wrap">
      <table class="obs-table">
        <thead><tr><th>時刻</th><th>イベント</th><th>ツール</th><th>起動元</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${totalPages > 1 ? _renderPager("evt", _evtRecentPage, totalPages, _evtRecentSize, total) : ""}`;
}

// ── ページャー ───────────────────────────────────────────────

function _renderPager(key, page, totalPages, size, total) {
  const startN = (page - 1) * size + 1;
  const endN = Math.min(page * size, total);

  const sizeOpts = [20, 50, 100].map(n =>
    `<option value="${n}" ${size === n ? "selected" : ""}>${n}件</option>`
  ).join("");

  // ページ番号ボタン（最大7個表示）
  let pageButtons = "";
  if (totalPages > 1) {
    const range = _calcPageRange(page, totalPages, 7);
    if (range[0] > 1) pageButtons += `<button class="obs-page-btn" onclick="_goPage('${key}',1)">1</button>`;
    if (range[0] > 2) pageButtons += '<span class="obs-page-dots">...</span>';
    for (const p of range) {
      const cls = p === page ? "obs-page-btn active" : "obs-page-btn";
      pageButtons += `<button class="${cls}" onclick="_goPage('${key}',${p})">${p}</button>`;
    }
    if (range[range.length - 1] < totalPages - 1) pageButtons += '<span class="obs-page-dots">...</span>';
    if (range[range.length - 1] < totalPages) pageButtons += `<button class="obs-page-btn" onclick="_goPage('${key}',${totalPages})">${totalPages}</button>`;
  }

  return `<div class="obs-pager">
    <span class="obs-pager-info">${startN}-${endN} / ${total}件</span>
    <div class="obs-pager-nav">
      <button class="obs-page-btn" onclick="_goPage('${key}',${page - 1})" ${page <= 1 ? "disabled" : ""}>&#9664;</button>
      ${pageButtons}
      <button class="obs-page-btn" onclick="_goPage('${key}',${page + 1})" ${page >= totalPages ? "disabled" : ""}>&#9654;</button>
    </div>
    <select class="obs-pager-size" onchange="_setPageSize('${key}',+this.value)">${sizeOpts}</select>
  </div>`;
}

function _calcPageRange(current, total, maxButtons) {
  const half = Math.floor(maxButtons / 2);
  let start = Math.max(1, current - half);
  let end = Math.min(total, start + maxButtons - 1);
  if (end - start + 1 < maxButtons) start = Math.max(1, end - maxButtons + 1);
  const range = [];
  for (let i = start; i <= end; i++) range.push(i);
  return range;
}

function _goPage(key, page) {
  if (key === "llm") {
    _llmRecentPage = Math.max(1, page);
    renderObservability();
  } else {
    _evtRecentPage = Math.max(1, page);
    renderObservability();
  }
}

function _setPageSize(key, size) {
  if (key === "llm") {
    _llmRecentSize = size;
    _llmRecentPage = 1;
  } else {
    _evtRecentSize = size;
    _evtRecentPage = 1;
  }
  renderObservability();
}

function _applyDateRange() {
  if (_obsFrom || _obsTo) {
    loadObservabilityData();
  }
}

function _resetObsDateRange() {
  _obsFrom = "";
  _obsTo = "";
  loadObservabilityData();
}

function _formatDate(date) {
  // ローカルタイムゾーン（JST）で日付を取得する（toISOString はUTCのため不可）
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function _escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
