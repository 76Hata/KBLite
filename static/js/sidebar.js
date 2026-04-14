// sidebar.js — サイドバー制御・セッション管理

// ── ページネーション状態 ────────────────────────────
let _sessionTotal = 0;
let _sessionOffset = 0;
const _SESSION_LIMIT = 50;

// ── サイドバー制御 ──────────────────────────────────
function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (window.innerWidth > 768) {
    // デスクトップ: collapsedクラスで開閉制御
    sidebar.classList.toggle('collapsed', !_sidebarOpen);
  } else {
    // モバイル: openクラスで開閉制御
    sidebar.classList.remove('open');
    sidebar.classList.add('collapsed');
  }
  loadSessions();
}

function toggleHeader() {
  const hdr = document.querySelector('header');
  const btn = document.getElementById('headerCollapseBtn');
  const collapsed = hdr.classList.toggle('collapsed');
  btn.textContent = collapsed ? '▼' : '▲';
  localStorage.setItem('headerCollapsed', collapsed ? '1' : '');
}

function toggleSidebar() {
  // ハンバーガーメニューの開閉（PC/モバイル共通）
  const menu = document.getElementById('mobMenu');
  if (menu && menu.classList.contains('open')) {
    closeMobMenu();
  } else {
    openMobMenu();
  }
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (window.innerWidth <= 768) {
    sidebar.classList.remove('open');
    sidebar.classList.add('collapsed');
    overlay.classList.remove('visible');
  }
}

// ウインドウリサイズ時にサイドバー状態を調整
window.addEventListener('resize', () => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (window.innerWidth > 768) {
    sidebar.classList.remove('open');
    sidebar.classList.toggle('collapsed', !_sidebarOpen);
    overlay.classList.remove('visible');
  } else {
    sidebar.classList.remove('open');
    sidebar.classList.add('collapsed');
    overlay.classList.remove('visible');
  }
});

// ── セッション一覧の読み込み・表示 ──────────────────
async function loadSessions(offset = 0) {
  const listEl = document.getElementById('sessionList');
  const loadingEl = document.getElementById('sessionLoading');
  if (loadingEl) loadingEl.style.display = 'block';

  const projectId = document.getElementById('projectFilter').value;
  const params = new URLSearchParams({ offset, limit: _SESSION_LIMIT });
  if (projectId) params.set('project_id', projectId);

  try {
    const res = await fetch('/api/sessions?' + params.toString());
    if (!res.ok) throw new Error('セッション一覧取得に失敗');
    const data = await res.json();
    _sessionOffset = offset;
    _sessionTotal = data.total ?? 0;
    renderSessionList(data.sessions || []);
    renderSessionPager();
  } catch (e) {
    console.error('セッション一覧エラー:', e);
    listEl.innerHTML = '<div class="session-empty">読み込みに失敗しました</div>';
  }
}

function renderSessionList(sessions) {
  const listEl = document.getElementById('sessionList');

  // ロック対象カテゴリ・プロジェクトのセッションを除外
  let filtered = sessions;
  if (_isLocked && _LOCKED_CATEGORIES.size > 0) {
    // カテゴリがロック対象のセッションを除外
    filtered = filtered.filter(s => !_LOCKED_CATEGORIES.has(s.category));
    // ロック対象プロジェクトに属するセッションも除外
    const lockedProjectIds = new Set(
      _projects
        .filter(p => _LOCKED_CATEGORY_NAMES.has(p.name) || _LOCKED_CATEGORIES.has(p.name))
        .map(p => p.id || p.project_id)
    );
    if (lockedProjectIds.size > 0) {
      filtered = filtered.filter(s => !s.project_id || !lockedProjectIds.has(s.project_id));
    }
  }

  if (filtered.length === 0) {
    listEl.innerHTML = '<div class="session-empty">会話履歴がありません</div>';
    return;
  }

  let html = '';
  for (const s of filtered) {
    const isActive = s.id === _sessionId || s.session_id === _sessionId;
    const title = esc(s.title || '無題の会話');
    const date = formatSessionDate(s.updated_at || s.created_at);
    const msgCount = s.message_count || 0;
    const sid = esc(s.id || s.session_id);
    const cat = s.category || '';
    const catLabel = _CATEGORY_LABELS[cat] || '';
    const catClass = cat && cat !== 'common_knowledge' ? ' cat-' + cat : '';
    const catBadge = catLabel && cat !== 'common_knowledge'
      ? '<span class="session-category-badge' + catClass + '">' + esc(catLabel) + '</span>'
      : '';
    const projName = s.project_id
      ? ((_projects.find(p => (p.id || p.project_id) === s.project_id) || {}).name || '')
      : '';
    const projBadge = projName
      ? '<span class="session-project-badge">' + esc(projName) + '</span>'
      : '';
    const forkNum = s.fork_number || 0;
    const forkBadge = forkNum > 0
      ? '<span class="session-fork-badge">fork #' + forkNum + '</span>'
      : '';
    const isBookmarked = !!s.bookmarked;
    const bookmarkBadge = isBookmarked
      ? '<span class="session-bookmark-badge" title="ブックマーク">★</span>'
      : '';
    const bookmarkLabel = isBookmarked ? 'ブックマーク解除' : 'ブックマーク';

    html += `
      <div class="session-item${isActive ? ' active' : ''}"
           data-session-id="${sid}"
           onclick="selectSession('${sid}')">
        <div class="session-item-content">
          <div class="session-item-title">${title}${bookmarkBadge}${catBadge}${forkBadge} <code style="font-size:10px;opacity:0.5;font-weight:normal;">${sid.slice(0,12)}</code><button class="conv-id-copy" title="IDをコピー" onclick="event.stopPropagation(); copyConvId(this, '${sid}')" style="font-size:10px;">&#x2398;</button></div>
          <div class="session-item-meta">${date} / ${msgCount}件${projBadge}</div>
        </div>
        <button class="session-item-menu-btn"
                onclick="event.stopPropagation(); toggleSessionMenu(this, '${sid}')"
                aria-label="メニュー" title="メニュー">&#x22EF;</button>
        <div class="session-menu" id="menu-${sid}">
          <div class="session-menu-item" onclick="event.stopPropagation(); toggleSessionBookmark('${sid}', ${isBookmarked ? 'false' : 'true'})">${bookmarkLabel}</div>
          <div class="session-menu-item" onclick="event.stopPropagation(); promptRenameSession('${sid}')">タイトル編集</div>
          <div class="session-menu-item" onclick="event.stopPropagation(); promptMoveSession('${sid}')">プロジェクトに移動</div>
          <div class="session-menu-divider"></div>
          <div class="session-menu-item danger" onclick="event.stopPropagation(); deleteSession('${sid}')">削除</div>
        </div>
      </div>
    `;
  }
  listEl.innerHTML = html;
}

// ── ページャー描画 ────────────────────────────────
function renderSessionPager() {
  let pagerEl = document.getElementById('sessionPager');
  if (!pagerEl) {
    pagerEl = document.createElement('div');
    pagerEl.id = 'sessionPager';
    pagerEl.style.cssText = [
      'display:flex', 'align-items:center', 'justify-content:space-between',
      'padding:6px 12px', 'border-top:1px solid #333',
      'font-size:12px', 'color:#888',
    ].join(';');
    const listEl = document.getElementById('sessionList');
    listEl.parentNode.insertBefore(pagerEl, listEl.nextSibling);
  }

  if (_sessionTotal <= _SESSION_LIMIT) {
    pagerEl.style.display = 'none';
    return;
  }

  pagerEl.style.display = 'flex';
  const from = _sessionOffset + 1;
  const to = Math.min(_sessionOffset + _SESSION_LIMIT, _sessionTotal);
  const prevOffset = _sessionOffset - _SESSION_LIMIT;
  const nextOffset = _sessionOffset + _SESSION_LIMIT;
  const hasPrev = _sessionOffset > 0;
  const hasNext = nextOffset < _sessionTotal;
  const btnStyle = (enabled) =>
    `background:none;border:1px solid ${enabled ? '#555' : '#3a3a3a'};` +
    `color:${enabled ? '#ccc' : '#555'};padding:3px 8px;border-radius:4px;` +
    `cursor:${enabled ? 'pointer' : 'default'};font-size:11px;`;

  pagerEl.innerHTML =
    `<button onclick="loadSessions(${prevOffset})" ${hasPrev ? '' : 'disabled'} style="${btnStyle(hasPrev)}">前へ</button>` +
    `<span>${from}〜${to} / ${_sessionTotal}件</span>` +
    `<button onclick="loadSessions(${nextOffset})" ${hasNext ? '' : 'disabled'} style="${btnStyle(hasNext)}">次へ</button>`;
}

// ── セッション選択（過去の会話を表示） ──────────────
async function selectSession(sessionId) {
  // 現在のアクティブセッション or 既に閲覧中の同じセッションなら何もしない
  if (sessionId === _sessionId && !_viewingHistory) {
    closeSidebar();
    return;
  }
  if (_viewingHistory && sessionId === _viewingSessionId) {
    closeSidebar();
    return;
  }

  const chat = document.getElementById('chat');
  chat.innerHTML = '<div class="session-loading">会話を読み込み中...</div>';

  try {
    const res = await fetch('/api/sessions/' + encodeURIComponent(sessionId));
    if (!res.ok) throw new Error('セッション取得に失敗');
    const data = await res.json();

    chat.innerHTML = '';

    if (data.conversations && data.conversations.length > 0) {
      for (const conv of data.conversations) {
        // 質問を表示
        if (conv.question) {
          appendMessage('user', '<p>' + esc(conv.question).replace(/\n/g, '<br>') + '</p>', false, { rawText: conv.question });
        }
        // 回答を表示（コピー/DLボタン付き）
        if (conv.answer) {
          const cleanAnswer = stripTitleTag(conv.answer);
          const title = conv.title || extractTitle(conv.answer);
          const titleHtml = buildTitleHtml(title, sessionId, conv.sequence);
          const div = appendMessage('assistant', titleHtml + mdToHtml(cleanAnswer), false, {
            rawMarkdown: cleanAnswer,
            question: conv.question || '',
            title: title || ''
          });
          if (conv.id) div.setAttribute('data-conv-id', conv.id);
          // タイトル編集ボタンを追加（過去会話表示時のみ）
          const titleEl = div.querySelector('.response-title');
          if (titleEl) {
            titleEl.appendChild(createTitleEditBtn(conv.id, titleEl));
          } else {
            // タイトルがない場合はプレースホルダ付きの編集ボタンを表示
            const mc2 = div.querySelector('.msg-content');
            if (mc2) {
              const placeholder = document.createElement('div');
              placeholder.className = 'title-placeholder';
              placeholder.innerHTML = '<button class="title-edit-btn" title="タイトルを追加">+ タイトルを追加</button>';
              placeholder.querySelector('button').addEventListener('click', () => editConvTitle(conv.id, placeholder, sessionId, conv.sequence));
              mc2.insertBefore(placeholder, mc2.firstChild);
            }
          }
          // Mermaid 図のレンダリング
          const mc = div.querySelector('.msg-content');
          if (mc) {
            await renderMermaidBlocks(mc);
            await renderDrawioBlocks(mc);
            addCodeBlockButtons(mc);
          }
        }
      }
    } else {
      chat.innerHTML = '<div class="state">この会話にはメッセージがありません。</div>';
    }

    // 読み取り専用モードに切り替え
    _viewingHistory = true;
    _viewingSessionId = sessionId;
    document.getElementById('readonlyBanner').classList.add('visible');
    document.getElementById('inputArea').classList.add('disabled');

    // サイドバーのアクティブ表示を更新
    updateActiveSession(sessionId);
    closeSidebar();

  } catch (e) {
    console.error('セッション取得エラー:', e);
    chat.innerHTML = '<div class="state" style="color:#c0392b">会話の読み込みに失敗しました。</div>';
  }
}

function updateActiveSession(activeId) {
  document.querySelectorAll('.session-item').forEach(el => {
    const sid = el.getAttribute('data-session-id');
    el.classList.toggle('active', sid === activeId);
  });
}

// ── セッション削除 ─────────────────────────────────
async function deleteSession(sessionId) {
  if (!confirm('この会話を削除しますか？')) return;

  try {
    const res = await fetch('/api/sessions/' + encodeURIComponent(sessionId), {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('削除に失敗');

    // 削除したのが現在表示中/閲覧中のセッションなら新しい会話にリセット
    if (sessionId === _sessionId || (_viewingHistory && sessionId === _viewingSessionId)) {
      newChat();
    }

    // セッション一覧を再読み込み
    loadSessions();

  } catch (e) {
    console.error('セッション削除エラー:', e);
    alert('会話の削除に失敗しました。');
  }
}

// ── セッションメニュー制御 ──────────────────────────
function toggleSessionMenu(btn, sessionId) {
  const menu = document.getElementById('menu-' + sessionId);
  if (!menu) return;
  // 他のメニューを閉じる
  document.querySelectorAll('.session-menu.open').forEach(m => {
    if (m !== menu) m.classList.remove('open');
  });
  menu.classList.toggle('open');
}

// グローバルクリックでメニューを閉じる
document.addEventListener('click', () => {
  document.querySelectorAll('.session-menu.open').forEach(m => m.classList.remove('open'));
});

async function toggleSessionBookmark(sessionId, bookmarked) {
  document.querySelectorAll('.session-menu.open').forEach(m => m.classList.remove('open'));
  try {
    const res = await fetch('/api/sessions/' + encodeURIComponent(sessionId) + '/bookmark', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookmarked }),
    });
    if (!res.ok) throw new Error('bookmark update failed');
    showToast(bookmarked ? 'ブックマークしました' : 'ブックマーク解除しました');
    loadSessions(_sessionOffset);
  } catch (e) {
    console.error('ブックマーク更新エラー:', e);
    showToast('ブックマーク更新に失敗しました');
  }
}
