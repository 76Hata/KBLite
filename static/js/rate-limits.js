// rate-limits.js — ヘッダーに 5h / 7d Rate Limits ゲージを表示

const _RL_POLL_INTERVAL = 3_600_000; // 1時間（毎時5分にスケジュール）
let _rlTimer = null;
let _clockTimer = null;

// ── ターン数警告（10ターンで新規チャット推奨） ─────────────────────────
const _TURN_WARNING_THRESHOLD = 10;

function _showTurnWarningDialog() {
  const overlay = document.createElement('div');
  overlay.id = 'turnWarningOverlay';
  overlay.style.cssText = [
    'position:fixed', 'inset:0', 'background:rgba(0,0,0,0.75)',
    'z-index:10000', 'display:flex', 'align-items:center', 'justify-content:center'
  ].join(';');
  const dlg = document.createElement('div');
  dlg.style.cssText = [
    'background:#1e1e2e', 'border:2px solid #f87171', 'border-radius:12px',
    'padding:28px 36px', 'max-width:420px', 'text-align:center', 'color:#fff',
    'box-shadow:0 8px 32px rgba(0,0,0,0.6)'
  ].join(';');
  dlg.innerHTML =
    '<div style="font-size:2.5em;margin-bottom:12px">&#x1F4AC;</div>' +
    '<h3 style="color:#f87171;margin:0 0 10px;font-size:1.1em">会話が10ターンを超えました</h3>' +
    '<p style="color:#aaa;margin:0 0 20px;font-size:0.88em;line-height:1.6">' +
    '会話が長くなるとプロンプトサイズが増大し、<br>コスト・応答精度に影響します。<br>新規チャットの開始を推奨します。' +
    '</p>' +
    '<button id="turnWarnCloseBtn" style="background:#f87171;border:none;color:#fff;' +
    'padding:8px 28px;border-radius:6px;cursor:pointer;font-size:0.95em">閉じる</button>';
  overlay.appendChild(dlg);
  document.body.appendChild(overlay);
  document.getElementById('turnWarnCloseBtn').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
}

function _checkTurnWarning(turnCount) {
  if (turnCount === _TURN_WARNING_THRESHOLD) {
    _showTurnWarningDialog();
  }
}

// ── ピークタイム表示 ───────────────────────────────────
// ピーク1: PT 5:00-11:00 AM weekdays（PDT=夏時間: UTC 12-18、PST=冬時間: UTC 13-19）
// ピーク2: UTC 22:00-03:00 (JST 07:00〜12:00) 平日のみ

/** 現在が太平洋夏時間（PDT, UTC-7）かどうかを返す */
function _isPacificDST() {
  try {
    const tzName = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Los_Angeles',
      timeZoneName: 'short'
    }).formatToParts(new Date()).find(p => p.type === 'timeZoneName').value;
    return tzName === 'PDT';
  } catch {
    // フォールバック: 3月第2日曜 2:00〜11月第1日曜 2:00 をPDTとして判定
    const now = new Date();
    const y = now.getFullYear();
    const dstStart = new Date(y, 2, 8  + (7 - new Date(y, 2,  8).getDay()) % 7, 2);
    const dstEnd   = new Date(y, 10, 1 + (7 - new Date(y, 10, 1).getDay()) % 7, 2);
    return now >= dstStart && now < dstEnd;
  }
}

/** 夏時間/冬時間に応じたピーク定義を返す（毎回評価して自動補正） */
function _getPeaks() {
  const dst = _isPacificDST();
  return [
    {
      id: 'peakInd1',
      startUTC: dst ? 12 : 13,
      endUTC:   dst ? 18 : 19,
      labelJST: dst ? '21:00〜03:00' : '22:00〜04:00',
    },
    { id: 'peakInd2', startUTC: 22, endUTC: 3, labelJST: '07:00〜12:00' },
  ];
}

let _peakCheckTimer = null;

function _isPeakTime(startUTC, endUTC) {
  const now = new Date();
  const dayUTC = now.getUTCDay(); // 0=Sun, 6=Sat
  if (dayUTC === 0 || dayUTC === 6) return false;
  const h = now.getUTCHours();
  // 日付またぎ（例: 22〜03）も正しく判定
  return startUTC < endUTC ? (h >= startUTC && h < endUTC)
                           : (h >= startUTC || h < endUTC);
}

// ピーク時（赤点灯）スタイル
const _PEAK_ACTIVE_CSS = [
  'background:#dc2626', 'color:#fff', 'border-radius:6px',
  'padding:2px 7px', 'font-size:0.74em', 'font-weight:bold',
  'display:inline-flex', 'align-items:center', 'gap:3px',
  'white-space:nowrap', 'user-select:none', 'cursor:default',
  'box-shadow:0 0 7px rgba(220,38,38,0.7)',
  'border:1px solid rgba(220,38,38,0.9)'
].join(';');

// オフピーク時（消灯グレー）スタイル
const _PEAK_IDLE_CSS = [
  'background:rgba(255,255,255,0.06)', 'color:rgba(255,255,255,0.28)',
  'border-radius:6px', 'border:1px solid rgba(255,255,255,0.12)',
  'padding:2px 7px', 'font-size:0.74em', 'font-weight:normal',
  'display:inline-flex', 'align-items:center', 'gap:3px',
  'white-space:nowrap', 'user-select:none', 'cursor:default'
].join(';');

function _updatePeakIndicators() {
  let anyActive = false;
  _getPeaks().forEach(({ id, startUTC, endUTC, labelJST }) => {
    const el = document.getElementById(id);
    if (!el) return;
    const active = _isPeakTime(startUTC, endUTC);
    if (active) {
      anyActive = true;
      el.style.cssText = _PEAK_ACTIVE_CSS;
      el.innerHTML = '<span style="font-size:1.1em">☠</span>' + labelJST;
      el.title = 'ピーク時間帯 JST ' + labelJST + '（平日 UTC ' + startUTC + ':00-' + endUTC + ':00）\nトークン消費が速くなる可能性があります';
    } else {
      el.style.cssText = 'display:none';
      el.textContent = '';
    }
  });
  // ピーク中のインジケーターが1つ以上あれば行全体を表示
  const container = document.getElementById('peakIndicators');
  if (container) container.style.display = anyActive ? 'flex' : 'none';
}

function _startPeakCheck() {
  _updatePeakIndicators();
  if (_peakCheckTimer) clearInterval(_peakCheckTimer);
  // 毎5分チェック（ピーク開始/終了を遅延なく反映）
  _peakCheckTimer = setInterval(_updatePeakIndicators, 5 * 60 * 1000);
}


// ── プロモーション判定 ──────────────────────────────────
// Claude March 2026 Usage Promotion: 3/13-3/28
// ピーク時間帯（通常レート）: 太平洋時間 5:00-11:00 AM (UTC 13:00-19:00)
// オフピーク（×2）: 上記以外
const _PROMO_START = new Date('2026-03-13T00:00:00-07:00'); // PDT
const _PROMO_END   = new Date('2026-03-29T00:00:00-07:00'); // 3/28 23:59 PDT
const _PEAK_START_UTC = 13; // UTC 13:00 = PDT 5:00 AM
const _PEAK_END_UTC   = 19; // UTC 19:00 = PDT 11:00 AM (weekdays only)

function _isPromoDouble() {
  const now = new Date();
  if (now < _PROMO_START || now >= _PROMO_END) return false;
  const dayUTC = now.getUTCDay(); // 0=Sun, 6=Sat
  // 週末はオフピーク扱い（終日×2）
  if (dayUTC === 0 || dayUTC === 6) return true;
  // 平日: ピーク時間帯以外が×2
  const hourUTC = now.getUTCHours();
  return hourUTC < _PEAK_START_UTC || hourUTC >= _PEAK_END_UTC;
}

function _rlColor(pct) {
  if (pct < 50) return '#4ade80'; // green
  if (pct < 80) return '#facc15'; // yellow
  return '#f87171'; // red
}

function _rlBgColor(pct) {
  if (pct < 50) return 'rgba(74,222,128,0.15)';
  if (pct < 80) return 'rgba(250,204,21,0.15)';
  return 'rgba(248,113,113,0.15)';
}

function _rlToMs(v) {
  // resets_at: Unix秒(number/string) or ISO文字列 → ミリ秒に統一
  if (!v) return 0;
  const n = Number(v);
  if (!isNaN(n) && n > 0) return n < 1e12 ? n * 1000 : n;
  return new Date(v).getTime() || 0;
}

function _rlFormatReset(resetAt) {
  const ms = _rlToMs(resetAt);
  if (!ms) return '';
  const d = new Date(ms);
  const h = d.getHours().toString().padStart(2, '0');
  const m = d.getMinutes().toString().padStart(2, '0');
  return h + ':' + m;
}

function _rlFormatCountdown(resetAt) {
  // 5h用: 残り時間を hh:mm でカウントダウン
  const ms = _rlToMs(resetAt);
  if (!ms) return '';
  const diff = ms - Date.now();
  if (diff <= 0) return '00:00';
  const h = Math.floor(diff / 3600000).toString().padStart(2, '0');
  const m = Math.floor((diff % 3600000) / 60000).toString().padStart(2, '0');
  return h + ':' + m;
}

function _rlFormatResetDate(resetAt) {
  // 7d用: リセット日時を mm/dd hh:mm で表示
  const ms = _rlToMs(resetAt);
  if (!ms) return '';
  const d = new Date(ms);
  const mo = (d.getMonth() + 1).toString().padStart(2, '0');
  const dd = d.getDate().toString().padStart(2, '0');
  const h = d.getHours().toString().padStart(2, '0');
  const mi = d.getMinutes().toString().padStart(2, '0');
  return mo + '/' + dd + ' ' + h + ':' + mi;
}

function _rlUpdateGauge(id, pct, resetAt) {
  const wrap = document.getElementById(id);
  if (!wrap) return;
  const bar = wrap.querySelector('.rl-bar-fill');
  const label = wrap.querySelector('.rl-pct');
  if (!bar || !label) return;

  const p = Math.min(100, Math.max(0, pct));
  bar.style.width = p + '%';
  bar.style.background = _rlColor(p);
  wrap.style.borderColor = _rlColor(p);
  wrap.style.background = _rlBgColor(p);
  label.textContent = p.toFixed(0) + '%';

  // 残り時間を保存（毎秒更新用）
  wrap.dataset.resetAt = resetAt || '';

  const reset = _rlFormatReset(resetAt);
  wrap.title = wrap.dataset.labelPrefix + ': ' + p.toFixed(1) + '%' +
    (reset ? ' (reset ' + reset + ')' : '');

  _rlUpdateRemaining(wrap);
}

function _rlUpdateRemaining(wrap) {
  const el = wrap.querySelector('.rl-remaining');
  if (!el) return;
  const ra = wrap.dataset.resetAt;
  if (wrap.id === 'rlGauge5h') {
    el.textContent = _rlFormatCountdown(ra);
  } else {
    el.textContent = _rlFormatResetDate(ra);
  }
}

function _rlUpdateAllRemaining() {
  document.querySelectorAll('.rl-gauge').forEach(_rlUpdateRemaining);
}

function _updatePromoMark() {
  const mark = document.getElementById('promoMark');
  if (!mark) return;
  const mobItem = document.getElementById('mobPromoItem');
  const now = new Date();
  if (now < _PROMO_START || now >= _PROMO_END) {
    mark.style.display = 'none';
    if (mobItem) mobItem.style.display = 'none';
    return;
  }
  mark.style.display = '';
  if (mobItem) mobItem.style.display = '';
  if (_isPromoDouble()) {
    mark.textContent = '×2';
    mark.style.background = 'linear-gradient(135deg,#f59e0b,#ef4444)';
    mark.style.color = '#fff';
    mark.style.animation = 'promoPulse 2s ease-in-out infinite';
    mark.title = 'Usage ×2 プロモーション中（オフピーク）';
  } else {
    mark.textContent = '×1';
    mark.style.background = 'rgba(255,255,255,0.15)';
    mark.style.color = '#aaa';
    mark.style.animation = 'none';
    mark.title = 'ピーク時間帯（通常レート）';
  }
}

// ── 利用許容値ライン ──────────────────────────────
const _HOURLY_RATE = 100 / (24 * 7); // ≈ 0.5952%/h

function _calcBudgetThreshold(resetsAt) {
  const ms = _rlToMs(resetsAt);
  if (!ms) return 100;
  const remainMs = ms - Date.now();
  if (remainMs <= 0) return 100;
  return (remainMs / 3600000) * _HOURLY_RATE;
}

/** 7dゲージにその日までの利用許容値ラインを表示 */
function _rlUpdateThreshold(resetsAt, usedPct) {
  const wrap = document.getElementById('rlGauge7d');
  if (!wrap) return;
  const line = wrap.querySelector('.rl-threshold-line');
  const valEl = wrap.querySelector('.rl-threshold-val');
  const threshold = _calcBudgetThreshold(resetsAt);
  const allowable = 100 - threshold;
  if (allowable <= 0) {
    if (line) line.style.display = 'none';
    if (valEl) valEl.textContent = '';
    return;
  }
  if (line) {
    line.style.display = '';
    line.style.left = Math.min(100, allowable) + '%';
  }
  if (valEl) {
    valEl.textContent = '(' + allowable.toFixed(0) + '%)';
    valEl.style.color = (usedPct != null && usedPct >= allowable) ? '#ff0000' : '#facc15';
  }
}

async function fetchRateLimits() {
  try {
    const res = await fetch('/api/rate-limits');
    if (!res.ok) return;           // 前回の表示を維持
    const data = await res.json();

    const container = document.getElementById('rlContainer');
    if (container) container.style.display = '';

    const five = data.five_hour || {};
    const seven = data.seven_day || {};

    if (five.used_percentage != null) {
      _rlUpdateGauge('rlGauge5h', five.used_percentage, five.resets_at);
    }
    if (seven.used_percentage != null) {
      _rlUpdateGauge('rlGauge7d', seven.used_percentage, seven.resets_at);
      // 利用許容値ライン更新
      _rlUpdateThreshold(seven.resets_at, seven.used_percentage);
    }

    _updatePromoMark();
  } catch {
    // ネットワークエラー等 — 前回の表示を維持
  }
}

// ── ヘッダー時計（秒単位）──────────────────────────────
function _updateClock() {
  const el = document.getElementById('headerClock');
  if (!el) return;
  const now = new Date();
  const y = now.getFullYear();
  const mo = (now.getMonth() + 1).toString().padStart(2, '0');
  const d = now.getDate().toString().padStart(2, '0');
  const h = now.getHours().toString().padStart(2, '0');
  const mi = now.getMinutes().toString().padStart(2, '0');
  const s = now.getSeconds().toString().padStart(2, '0');
  el.textContent = y + '/' + mo + '/' + d + ' ' + h + ':' + mi + ':' + s;
}

function _scheduleNextHour() {
  // 次の毎時5分0秒までのミリ秒を算出してタイマー設定
  const now = new Date();
  const next = new Date(now);
  if (now.getMinutes() >= 5) {
    next.setHours(now.getHours() + 1, 5, 0, 0);
  } else {
    next.setMinutes(5, 0, 0);
  }
  const delay = next - now;
  if (_rlTimer) clearTimeout(_rlTimer);
  _rlTimer = setTimeout(() => {
    fetchRateLimits();
    // 以降は1時間ごと
    _rlTimer = setInterval(fetchRateLimits, _RL_POLL_INTERVAL);
  }, delay);
}

function startRateLimitsPolling() {
  fetchRateLimits();       // 初回即時取得
  _scheduleNextHour();     // 次の毎時5分から1時間間隔

  // 時計＋残り時間を毎秒更新
  _updateClock();
  _rlUpdateAllRemaining();
  if (_clockTimer) clearInterval(_clockTimer);
  _clockTimer = setInterval(() => { _updateClock(); _rlUpdateAllRemaining(); }, 1000);

  // ピークタイム表示
  _startPeakCheck();
}

// 初期化
startRateLimitsPolling();
