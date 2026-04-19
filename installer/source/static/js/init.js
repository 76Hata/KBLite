// init.js — 初期化コード（最後に読み込む）

// _sessionId を generateUUID() で初期化
_sessionId = generateUUID();

// textarea 自動リサイズ（リサイザーで手動設定後は停止）
const msgInput = document.getElementById('messageInput');
let _manualResized = false;
msgInput.addEventListener('input', () => {
  if (_manualResized) return;
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 300) + 'px';
});

// ── 入力欄リサイザー（境界線ドラッグ） ──────────────────
(function() {
  const resizer = document.getElementById('inputResizer');
  const chatView = document.getElementById('chatView');
  if (!resizer || !chatView) return;
  let dragging = false;

  resizer.addEventListener('mousedown', (e) => {
    e.preventDefault();
    dragging = true;
    _manualResized = true;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const viewRect = chatView.getBoundingClientRect();
    const newH = viewRect.bottom - e.clientY - 6; // 6 = resizer height
    const clamped = Math.max(42, Math.min(newH, viewRect.height * 0.7));
    msgInput.style.height = clamped + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  // タッチ対応
  resizer.addEventListener('touchstart', (e) => {
    dragging = true;
    _manualResized = true;
    resizer.classList.add('dragging');
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    const touch = e.touches[0];
    const viewRect = chatView.getBoundingClientRect();
    const newH = viewRect.bottom - touch.clientY - 6;
    const clamped = Math.max(42, Math.min(newH, viewRect.height * 0.7));
    msgInput.style.height = clamped + 'px';
  }, { passive: true });

  document.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove('dragging');
  });
})();

// Ctrl+Enter で送信（Enter は常に改行）
msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.isComposing) {
    e.preventDefault();
    sendMessage();
  }
});

// バックグラウンド復帰: タブが再びアクティブになった時にタスク結果を取得
document.addEventListener('visibilitychange', async () => {
  if (document.visibilityState === 'visible' && _activeTaskId && _sending && !_recovering) {
    _recovering = true;
    const chat = document.getElementById('chat');
    const aiDiv = chat.querySelector('.msg.assistant.typing');
    if (!aiDiv) { _recovering = false; return; }
    const aiContent = aiDiv.querySelector('.msg-content');
    if (!aiContent) { _recovering = false; return; }
    // sendMessage 内の question を取得（直前のユーザーメッセージ）
    const userMsgs = chat.querySelectorAll('.msg.user');
    const lastUserMsg = userMsgs[userMsgs.length - 1];
    const question = lastUserMsg ? lastUserMsg.querySelector('.msg-content')?.textContent?.trim() || '' : '';
    console.log('タブ復帰、ポーリングで結果取得を試みます: task=' + _activeTaskId);
    const recovered = await recoverTask(_activeTaskId, aiContent, aiDiv, question);
    _recovering = false;
    if (recovered) {
      hideWaitingIndicator();
      _activeTaskId = null;
      _sending = false;
      _cancelled = false;
      setSendMode();
    }
  }
});

// 画像クリックで新しいタブに拡大表示
document.getElementById('chat').addEventListener('click', (e) => {
  if (e.target.tagName === 'IMG' && e.target.closest('.msg-content')) {
    window.open(e.target.src, '_blank');
  }
});

// スクロール位置に応じてボタンの表示/非表示を切り替え
document.addEventListener('DOMContentLoaded', () => {
  const chat = document.getElementById('chat');
  const btn = document.getElementById('scrollTopBtn');
  chat.addEventListener('scroll', () => {
    btn.classList.toggle('visible', chat.scrollTop > 300);
  });

  // RAGダイアログ: Enterキーで検索実行
  document.getElementById('ragDlgQuery').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) {
      e.preventDefault();
      executeRagSearch();
    }
  });
  // RAGダイアログ: オーバーレイクリックで閉じる
  document.getElementById('ragDlgOverlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeRagDialog();
  });
});

// ── 初期化 ─────────────────────────────────────────
// config.jsのloadAppConfig()完了を待ってから初期化（レースコンディション防止）
(async () => {
  if (typeof _configReady !== 'undefined') {
    await _configReady;
  }
  loadProjects();
  initSidebar();
})();

// ヘッダ折りたたみ状態の復元
if (localStorage.getItem('headerCollapsed') === '1') {
  document.querySelector('header').classList.add('collapsed');
  document.getElementById('headerCollapseBtn').textContent = '▼';
}

// ── モバイルハンバーガーメニュー ───────────────────────
function openMobMenu() {
  syncMobMenuState();
  if (typeof updateMobMenuLock === 'function') updateMobMenuLock();
  document.getElementById('mobMenu').classList.add('open');
  document.getElementById('mobMenuOverlay').classList.add('open');
}
function closeMobMenu() {
  document.getElementById('mobMenu').classList.remove('open');
  document.getElementById('mobMenuOverlay').classList.remove('open');
}
function openMobSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (window.innerWidth <= 768) {
    // モバイル: overlay付きで開く
    const overlay = document.getElementById('sidebarOverlay');
    sidebar.classList.add('open');
    sidebar.classList.remove('collapsed');
    overlay.classList.add('visible');
  } else {
    // PC: collapsedトグル
    const isCollapsed = sidebar.classList.contains('collapsed');
    sidebar.classList.toggle('collapsed', !isCollapsed);
    _sidebarOpen = isCollapsed;
  }
}
// ロックボタン状態同期（メニュー開時に更新）
function updateMobMenuLock() {
  const mobBtn = document.getElementById('mobMenuLockBtn');
  if (!mobBtn) return;
  const label = typeof _isLocked !== 'undefined' && _isLocked ? 'ロック中' : 'アンロック中';
  const svg = typeof _isLocked !== 'undefined' && _isLocked
    ? '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
    : '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 5-5 5 5 0 0 1 5 5"/></svg>';
  mobBtn.innerHTML = svg + ' ' + label;
}

function syncMobMenuState() {
  const headerSearchAll = document.getElementById('searchAllCheck');
  const mobSearchAll = document.getElementById('mobMenuSearchAllCheck');
  if (headerSearchAll && mobSearchAll) {
    mobSearchAll.checked = headerSearchAll.checked;
  }
}

function syncSearchAllFromMobMenu(checked) {
  const headerSearchAll = document.getElementById('searchAllCheck');
  if (headerSearchAll) {
    headerSearchAll.checked = checked;
  }
}

// ☰ボタン: モバイルはmobMenu、PCはサイドバーを開く
function handleSidebarToggle() {
  if (window.innerWidth <= 768) {
    openMobMenu();
  } else {
    toggleSidebar();
  }
}
