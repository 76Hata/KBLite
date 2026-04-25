// core.js — 共有状態変数 + ユーティリティ関数 + レンダリングヘルパー

// ── サーバー接続監視 & 自動再接続 ──────────────────────
let _serverOnline = true;
let _reconnectBanner = null;

function _createReconnectBanner() {
  if (_reconnectBanner) return;
  _reconnectBanner = document.createElement('div');
  _reconnectBanner.id = 'reconnect-banner';
  _reconnectBanner.style.cssText =
    'position:fixed;top:0;left:0;right:0;z-index:9999;padding:10px 16px;' +
    'background:#e74c3c;color:#fff;text-align:center;font-size:14px;font-weight:bold;' +
    'transition:background 0.5s;';
  _reconnectBanner.textContent = 'サーバーに再接続中...';
  document.body.appendChild(_reconnectBanner);
}

function _removeReconnectBanner() {
  if (!_reconnectBanner) return;
  _reconnectBanner.style.background = '#27ae60';
  _reconnectBanner.textContent = '再接続しました';
  setTimeout(() => {
    if (_reconnectBanner && _reconnectBanner.parentNode) {
      _reconnectBanner.parentNode.removeChild(_reconnectBanner);
    }
    _reconnectBanner = null;
  }, 2000);
}

async function _checkServerHealth() {
  try {
    const res = await fetch('/health', { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      if (!_serverOnline) {
        _serverOnline = true;
        _removeReconnectBanner();
        console.log('サーバー再接続OK');
      }
      return true;
    }
  } catch (_) {}
  if (_serverOnline) {
    _serverOnline = false;
    _createReconnectBanner();
    console.warn('サーバー接続断');
  }
  return false;
}

// 30秒間隔でヘルスチェック（切断検知時は5秒間隔に切替）
setInterval(async () => {
  const ok = await _checkServerHealth();
  if (!ok) {
    // 切断中は5秒間隔でリトライ
    const retryId = setInterval(async () => {
      if (await _checkServerHealth()) clearInterval(retryId);
    }, 5000);
    // 5分で諦め（300秒 / 5秒 = 60回）
    setTimeout(() => clearInterval(retryId), 300000);
  }
}, 30000);

// ── 設定のAPI読み込みとセレクトボックス動的構築 ────
let _TEAM_DEFAULT_MODELS = {};
let _TEAM_CATEGORY_MAP = {};
// パスワード認証は毎回要求する

// 設定データをキャッシュ（ロック切替時に再構築するため）
let _configCache = null;

let _sending = false;
let _activeTaskId = null;
let _currentReader = null;  // SSEストリームのreader（中止用）
let _cancelled = false;      // 中止リクエスト済みフラグ
let _recovering = false;     // ポーリング復帰中フラグ（重複防止）
let _messageSaved = false;   // 会話保存済みフラグ（二重保存防止）
let _viewingHistory = false;  // 過去の会話を表示中かどうか
let _viewingSessionId = null; // 閲覧中のセッションID（過去の会話表示時のみ）

let _sessionId = null;
let _sequence = 0;
let _sessionCreated = false;
let _sessionCategory = '';  // 初回送信時にカテゴリセレクタから取得
let _conversationHistory = [];  // [{question, answer}, ...]
let _claudeSessionId = '';    // Claude CLI session_id（最後のレスポンスから取得）
let _forkFromSessionId = '';  // 分岐元のClaude session_id（分岐時のみ設定）
let _parentSessionId = '';    // 分岐元セッションID（セッション作成時にparent_session_idとして保存）

// カテゴリ表示名マップ（loadAppConfigで動的構築）
let _CATEGORY_LABELS = {};
// ロック対象カテゴリのsystem_idセット（loadAppConfigで構築）
let _LOCKED_CATEGORIES = new Set();
// ロック対象カテゴリの名前セット（プロジェクトフィルタ用）
let _LOCKED_CATEGORY_NAMES = new Set();
// ロック状態（true=ロック中=locked項目を非表示）
let _isLocked = true;

let _mermaidCounter = 0;
let _drawioLoadPromise = null;

// ── 図の拡大表示ライトボックス ──────────────────────────
let _lbZoom = 1;
let _lbPanX = 0, _lbPanY = 0;
let _lbDragging = false;
let _lbDragStart = { x: 0, y: 0 };
let _lbSvgW = 0, _lbSvgH = 0;

function openDiagramLightbox(svgEl) {
  const lb = document.getElementById('diagramLightbox');
  const content = document.getElementById('diagramLightboxContent');
  const clone = svgEl.cloneNode(true);
  clone.removeAttribute('style');
  clone.style.maxWidth = 'none';
  clone.style.maxHeight = 'none';
  content.innerHTML = '';
  content.appendChild(clone);

  // SVGの実サイズを取得（viewBox > getBBox > attribute > fallback）
  const vb = clone.viewBox?.baseVal;
  const bbox = svgEl.getBBox ? svgEl.getBBox() : null;
  const svgNatW = (vb && vb.width > 0) ? vb.width : (bbox ? bbox.width : parseFloat(clone.getAttribute('width')) || 800);
  const svgNatH = (vb && vb.height > 0) ? vb.height : (bbox ? bbox.height : parseFloat(clone.getAttribute('height')) || 600);

  // ビューポートの90%にフィットする初期スケールを計算
  const vpW = window.innerWidth * 0.9;
  const vpH = window.innerHeight * 0.85;
  const fitScale = Math.min(vpW / svgNatW, vpH / svgNatH);

  // _lbSvgW/H はフィット後のベースサイズ（zoom=1でこのサイズ）
  _lbSvgW = svgNatW * fitScale;
  _lbSvgH = svgNatH * fitScale;
  _lbZoom = 1;
  _lbPanX = 0;
  _lbPanY = 0;
  _applyLbTransform(clone);

  lb.classList.add('open');
  document.addEventListener('keydown', _lbKeyHandler);

  // ドラッグでパン
  content.onmousedown = (e) => { _lbDragging = true; _lbDragStart = { x: e.clientX - _lbPanX, y: e.clientY - _lbPanY }; content.classList.add('dragging'); };
  content.onmousemove = (e) => { if (!_lbDragging) return; _lbPanX = e.clientX - _lbDragStart.x; _lbPanY = e.clientY - _lbDragStart.y; _applyLbTransform(content.querySelector('svg')); };
  content.onmouseup = content.onmouseleave = () => { _lbDragging = false; content.classList.remove('dragging'); };

  // マウスホイールでズーム
  content.onwheel = (e) => { e.preventDefault(); diagramZoom(e.deltaY < 0 ? 0.15 : -0.15); };

  // タッチ操作（ピンチズーム）
  let _lbTouchDist = 0;
  content.ontouchstart = (e) => {
    if (e.touches.length === 2) {
      _lbTouchDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
    } else if (e.touches.length === 1) {
      _lbDragging = true;
      _lbDragStart = { x: e.touches[0].clientX - _lbPanX, y: e.touches[0].clientY - _lbPanY };
    }
  };
  content.ontouchmove = (e) => {
    e.preventDefault();
    if (e.touches.length === 2) {
      const dist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
      if (_lbTouchDist > 0) diagramZoom((dist - _lbTouchDist) * 0.005);
      _lbTouchDist = dist;
    } else if (e.touches.length === 1 && _lbDragging) {
      _lbPanX = e.touches[0].clientX - _lbDragStart.x;
      _lbPanY = e.touches[0].clientY - _lbDragStart.y;
      _applyLbTransform(content.querySelector('svg'));
    }
  };
  content.ontouchend = () => { _lbDragging = false; _lbTouchDist = 0; };
}

function closeDiagramLightbox() {
  document.getElementById('diagramLightbox').classList.remove('open');
  document.removeEventListener('keydown', _lbKeyHandler);
}

function diagramZoom(delta) {
  _lbZoom = Math.max(0.2, Math.min(5, _lbZoom + delta));
  const svg = document.querySelector('#diagramLightboxContent svg');
  if (svg) _applyLbTransform(svg);
  document.getElementById('diagramZoomInfo').textContent = Math.round(_lbZoom * 100) + '%';
}

function diagramZoomReset() {
  _lbZoom = 1; _lbPanX = 0; _lbPanY = 0;
  const svg = document.querySelector('#diagramLightboxContent svg');
  if (svg) _applyLbTransform(svg);
  document.getElementById('diagramZoomInfo').textContent = '100%';
}

function _applyLbTransform(svg) {
  if (!svg) return;
  const cw = window.innerWidth, ch = window.innerHeight;
  const w = _lbSvgW * _lbZoom, h = _lbSvgH * _lbZoom;
  const x = (cw - w) / 2 + _lbPanX;
  const y = (ch - h) / 2 + _lbPanY;
  svg.style.width = w + 'px';
  svg.style.height = h + 'px';
  svg.style.position = 'absolute';
  svg.style.left = x + 'px';
  svg.style.top = y + 'px';
  svg.style.transform = 'none';
}

function _lbKeyHandler(e) {
  if (e.key === 'Escape') closeDiagramLightbox();
  if (e.key === '+' || e.key === '=') diagramZoom(0.2);
  if (e.key === '-') diagramZoom(-0.2);
  if (e.key === '0') diagramZoomReset();
}
let _sidebarOpen = window.innerWidth > 768;  // デスクトップでは初期表示

let _elapsedTimer = null;
let _waitStartTime = null;
let _waitStatusText = '応答を待っています...';
/** 送信中の /api/team-chat の ai_service（SSE の task_id と DOM のズレ対策） */
let _activeRequestAiService = '';

let _attachments = []; // [{name, content, type}]  type: "text" | "image"

let _logOffset = 0;
let _logDebounceTimer = null;

let _projects = [];  // {id, name, ...}
let _allSessions = [];  // フィルタ前の全セッション

var _isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

const _ATTACH_MAX_SIZE_TEXT  = 10 * 1024 * 1024; // テキスト 10MB
const _ATTACH_MAX_SIZE_IMAGE = 10 * 1024 * 1024; // 画像 10MB
const _ATTACH_MAX_FILES = 5;
const _IMAGE_TYPES = new Set(['image/png','image/jpeg','image/gif','image/webp']);

const _sendIcon = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
const _cancelIcon = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>';

const _TITLE_ICON_SVG = '<svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';

const _langExtMap = {
  javascript: 'js', typescript: 'ts', python: 'py', ruby: 'rb',
  java: 'java', kotlin: 'kt', swift: 'swift', go: 'go', rust: 'rs',
  php: 'php', csharp: 'cs', cpp: 'cpp', c: 'c', html: 'html',
  css: 'css', json: 'json', yaml: 'yaml', yml: 'yml', xml: 'xml',
  sql: 'sql', bash: 'sh', shell: 'sh', powershell: 'ps1',
  dockerfile: 'Dockerfile', markdown: 'md', toml: 'toml', ini: 'ini',
  dart: 'dart', scala: 'scala', lua: 'lua', perl: 'pl', r: 'r',
};

// ── ユーティリティ関数 ────────────────────────────

function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// marked.js の設定（リンクは全て別タブで開く）
const renderer = new marked.Renderer();
renderer.link = function({ href, title, text }) {
  const titleAttr = title ? ' title="' + title + '"' : '';
  return '<a href="' + href + '" target="_blank" rel="noopener noreferrer"' + titleAttr + '>' + text + '</a>';
};
marked.setOptions({ breaks: true, gfm: true, renderer });

// Mermaid.js の初期化（自動起動は無効化、エラー表示を抑制）
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  suppressErrorRendering: true,
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    padding: 15
  }
});

function mdToHtml(text) {
  return marked.parse(text);
}

function scrollToBottom() {
  const chat = document.getElementById('chat');
  chat.scrollTop = chat.scrollHeight;
}

function scrollToTop() {
  const chat = document.getElementById('chat');
  chat.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── トースト通知 ───────────────────────────────────
function showToast(message) {
  // 既存のトーストがあれば除去
  const existing = document.querySelector('.toast-notification');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast-notification';
  toast.textContent = message;
  document.body.appendChild(toast);

  // 表示アニメーション
  requestAnimationFrame(() => {
    toast.classList.add('visible');
  });

  // 2秒後に消去
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

function formatSessionDate(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHour = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);

    if (diffMin < 1) return 'たった今';
    if (diffMin < 60) return diffMin + '分前';
    if (diffHour < 24) return diffHour + '時間前';
    if (diffDay < 7) return diffDay + '日前';

    const month = d.getMonth() + 1;
    const day = d.getDate();
    if (d.getFullYear() === now.getFullYear()) {
      return month + '/' + day;
    }
    return d.getFullYear() + '/' + month + '/' + day;
  } catch (e) {
    return '';
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatLogDate(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const pad = n => String(n).padStart(2, '0');
    return d.getFullYear() + '/' + pad(d.getMonth() + 1) + '/' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  } catch (e) {
    return '';
  }
}

// ── ダウンロードユーティリティ ──────────────────────
function downloadBlob(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType + ';charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(filename + ' をダウンロードしました');
}

// ── レンダリングヘルパー ──────────────────────────

// コンテナ内の mermaid コードブロックを図に変換
async function renderMermaidBlocks(container) {
  const codeBlocks = container.querySelectorAll('pre > code.language-mermaid');
  if (codeBlocks.length === 0) return;

  mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    suppressErrorRendering: true,
    flowchart: { useMaxWidth: true, htmlLabels: true, padding: 15 }
  });

  for (const code of codeBlocks) {
    const pre = code.parentElement;
    const graphDef = code.textContent.replace(/\\u([0-9A-Fa-f]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));

    try {
      // 構文チェック（DOM要素を生成しない）
      await mermaid.parse(graphDef);
      // 構文が正しい場合のみレンダリング
      const id = 'mermaid-' + Date.now() + '-' + (++_mermaidCounter);
      const { svg } = await mermaid.render(id, graphDef);
      const wrapper = document.createElement('div');
      wrapper.className = 'mermaid';
      wrapper.innerHTML = svg;

      // クリックで拡大表示
      wrapper.addEventListener('click', (e) => {
        if (e.target.closest('.diagram-dl-toolbar')) return; // ツールバーのクリックは除外
        const svgEl = wrapper.querySelector('svg');
        if (svgEl) openDiagramLightbox(svgEl);
      });

      // ダウンロードツールバー
      const toolbar = document.createElement('div');
      toolbar.className = 'diagram-dl-toolbar';
      const svgBtn = document.createElement('button');
      svgBtn.textContent = 'SVG';
      svgBtn.addEventListener('click', () => downloadBlob(svg, 'diagram.svg', 'image/svg+xml'));
      const pngBtn = document.createElement('button');
      pngBtn.textContent = 'PNG';
      pngBtn.addEventListener('click', () => svgToPng(wrapper.querySelector('svg'), 'diagram.png'));
      toolbar.appendChild(svgBtn);
      toolbar.appendChild(pngBtn);
      wrapper.appendChild(toolbar);

      pre.replaceWith(wrapper);
    } catch (e) {
      console.warn('Mermaid: 構文エラーのためコードブロックを維持', e);
      // parse() はDOM要素を生成しないので後片付け不要
      // 元の pre/code をそのまま残す
    }
  }
  // 万が一残ったエラー要素をクリーンアップ
  document.querySelectorAll('[id^="dmermaid-"]').forEach(el => el.remove());
}

// ── draw.io 遅延ローダー & レンダリング ──────────────
function loadDrawioViewer() {
  if (typeof GraphViewer !== 'undefined') return Promise.resolve();
  if (_drawioLoadPromise) return _drawioLoadPromise;
  _drawioLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://viewer.diagrams.net/js/viewer-static.min.js';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('draw.io viewer の読み込みに失敗'));
    document.head.appendChild(script);
  });
  return _drawioLoadPromise;
}

async function renderDrawioBlocks(container) {
  const codeBlocks = container.querySelectorAll('pre > code.language-drawio');
  if (codeBlocks.length === 0) return;

  try {
    await loadDrawioViewer();
  } catch (e) {
    console.warn('draw.io viewer ロード失敗:', e);
    return;
  }

  for (const code of codeBlocks) {
    const pre = code.parentElement;
    const xmlContent = code.textContent.trim();

    try {
      const wrapper = document.createElement('div');
      wrapper.className = 'drawio-diagram';

      // draw.io で開くリンク
      const toolbar = document.createElement('div');
      toolbar.className = 'drawio-toolbar';
      const editLink = document.createElement('a');
      editLink.textContent = 'draw.io で開く';
      editLink.target = '_blank';
      editLink.rel = 'noopener';
      editLink.href = 'https://app.diagrams.net/?splash=0#R' + btoa(unescape(encodeURIComponent(xmlContent)));
      toolbar.appendChild(editLink);
      const xmlDlBtn = document.createElement('a');
      xmlDlBtn.textContent = 'XML DL';
      xmlDlBtn.style.cursor = 'pointer';
      xmlDlBtn.addEventListener('click', () => downloadBlob(xmlContent, 'diagram.drawio', 'application/xml'));
      toolbar.appendChild(xmlDlBtn);
      wrapper.appendChild(toolbar);

      const mxgraphDiv = document.createElement('div');
      mxgraphDiv.className = 'mxgraph';
      mxgraphDiv.setAttribute('data-mxgraph', JSON.stringify({
        highlight: '#0000ff',
        nav: true,
        resize: true,
        toolbar: 'zoom layers lightbox',
        xml: xmlContent,
      }));
      wrapper.appendChild(mxgraphDiv);
      pre.replaceWith(wrapper);
    } catch (e) {
      console.warn('draw.io: DOM構築エラー', e);
    }
  }

  // 新しい .mxgraph 要素をdraw.ioビューアで処理
  try {
    GraphViewer.processElements();
  } catch (e) {
    console.warn('draw.io: GraphViewer.processElements エラー', e);
  }
}

function svgToPng(svgEl, filename) {
  if (!svgEl) return;
  const svgData = new XMLSerializer().serializeToString(svgEl);
  const canvas = document.createElement('canvas');
  const bbox = svgEl.getBoundingClientRect();
  const scale = 2;
  canvas.width = bbox.width * scale;
  canvas.height = bbox.height * scale;
  const ctx = canvas.getContext('2d');
  const img = new Image();
  img.onload = () => {
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast(filename + ' をダウンロードしました');
    }, 'image/png');
  };
  img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
}

// ── コードブロックにダウンロードボタンを付与 ────────
// ── クリップボード フォールバック（title.js / export.js から共通利用） ──
function copyViaExecCommand(text, btn, onSuccess) {
  try {
    // 一時的な textarea を作成
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '-9999px';
    document.body.appendChild(textarea);

    // テキストを選択してコピー
    textarea.select();
    const success = document.execCommand('copy');
    document.body.removeChild(textarea);

    if (success) {
      if (onSuccess) { onSuccess(); } else { showCopySuccess(btn); }
    } else {
      showToast('コピーに失敗しました');
    }
  } catch (e) {
    console.error('コピー処理エラー:', e);
    showToast('コピーに失敗しました');
  }
}

function addCodeBlockButtons(container) {
  const preBlocks = container.querySelectorAll('pre > code[class*="language-"]');
  for (const code of preBlocks) {
    const pre = code.parentElement;
    if (pre.querySelector('.code-dl-toolbar')) continue;

    const cls = [...code.classList].find(c => c.startsWith('language-'));
    if (!cls) continue;
    const lang = cls.replace('language-', '');

    // mermaid / drawio は図として処理済み
    if (lang === 'mermaid' || lang === 'drawio') continue;

    const ext = _langExtMap[lang] || lang;
    const toolbar = document.createElement('div');
    toolbar.className = 'code-dl-toolbar';

    // コピーボタン
    const copyBtn = document.createElement('button');
    copyBtn.className = 'code-dl-btn';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', () => {
      const text = code.textContent;
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = 'Copied!';
        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1500);
      }).catch(() => showToast('コピーに失敗しました'));
    });

    // ダウンロードボタン
    const dlBtn = document.createElement('button');
    dlBtn.className = 'code-dl-btn';
    dlBtn.textContent = 'DL .' + ext;
    dlBtn.addEventListener('click', () => {
      const text = code.textContent;
      downloadBlob(text, 'code.' + ext, 'text/plain');
    });

    toolbar.appendChild(copyBtn);
    toolbar.appendChild(dlBtn);
    pre.appendChild(toolbar);
  }
}
