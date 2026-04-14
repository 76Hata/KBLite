// config.js — 設定読み込み・ロック・パスワード・チーム切替

/** /api/config に ai_services が無い・空のとき用（古いサーバでも表示されるようにする） */
const _FALLBACK_AI_SERVICES = [
  { id: 'claude', name: 'Claude Code', default: true },
  { id: 'cursor', name: 'Cursor Agent' },
];

async function loadAppConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    _configCache = await res.json();

    // カテゴリラベルマップ・ロック対象セットを構築
    _CATEGORY_LABELS = {};
    _LOCKED_CATEGORIES = new Set();
    _LOCKED_CATEGORY_NAMES = new Set();
    (_configCache.categories || []).forEach(c => {
      _CATEGORY_LABELS[c.system_id] = c.name;
      if (c.locked) {
        _LOCKED_CATEGORIES.add(c.system_id);
        _LOCKED_CATEGORY_NAMES.add(c.name);
      }
    });

    // ワークスペースプロジェクトセレクト構築
    const projSel = document.getElementById('workspaceProjectSelect');
    projSel.innerHTML = '';
    (_configCache.workspace_projects || []).forEach((p, i) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      if (i === 0) opt.selected = true;
      projSel.appendChild(opt);
    });

    // チーム連動マップ構築
    const teamSel = document.getElementById('teamSelect');
    teamSel.innerHTML = '';
    (_configCache.teams || []).forEach((t, i) => {
      const opt = document.createElement('option');
      opt.value = t.id;
      opt.textContent = t.name;
      if (i === 0) opt.selected = true;
      teamSel.appendChild(opt);
      _TEAM_DEFAULT_MODELS[t.id] = t.default_model || '';
      _TEAM_CATEGORY_MAP[t.id] = t.default_category || '';
    });

    // モデルセレクト構築
    const modelSel = document.getElementById('modelSelect');
    modelSel.innerHTML = '';
    (_configCache.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name;
      if (m.default) opt.selected = true;
      modelSel.appendChild(opt);
    });

    // AI サービス（Claude Code / Cursor Agent 等）— 送信ごとに CLI を切替
    const aiSvcSel = document.getElementById('aiServiceSelect');
    if (aiSvcSel) {
      aiSvcSel.innerHTML = '';
      let aiServices = _configCache.ai_services;
      if (!Array.isArray(aiServices) || aiServices.length === 0) {
        aiServices = _FALLBACK_AI_SERVICES;
      }
      aiServices.forEach((s) => {
        const opt = document.createElement('option');
        opt.value = s.id || '';
        opt.textContent = s.name || s.label || s.id || '';
        if (s.default) opt.selected = true;
        aiSvcSel.appendChild(opt);
      });
      try {
        const saved = localStorage.getItem('ka_ai_service');
        if (saved && [...aiSvcSel.options].some(o => o.value === saved)) {
          aiSvcSel.value = saved;
        }
      } catch (e) { /* ignore */ }
    }

    // ロック状態を適用してセレクトを構築
    applyLockState();

    // デフォルトプロジェクトのチーム・カテゴリを適用
    onWorkspaceProjectChange();
    updateWorkspaceCwdHint();
  } catch (e) {
    console.error('設定読み込みエラー:', e);
  }
}

/** 選択中の AI サービスに応じた CLI 作業ディレクトリをワークスペースセレクトの title に表示 */
function updateWorkspaceCwdHint() {
  const projSel = document.getElementById('workspaceProjectSelect');
  const aiSel = document.getElementById('aiServiceSelect');
  if (!projSel || !_configCache) return;
  const pid = projSel.value;
  const projects = _configCache.workspace_projects || [];
  const proj = projects.find(p => p.id === pid);
  if (!proj) return;
  const svc = aiSel && aiSel.value ? aiSel.value : 'claude';
  const path = svc === 'cursor'
    ? (proj.resolved_cwd_cursor || proj.cwd || '')
    : (proj.resolved_cwd_claude || proj.cwd || '');
  const label = svc === 'cursor' ? 'Cursor Agent cwd' : 'Claude Code cwd';
  projSel.title = path ? `${label}: ${path}` : '';
}

// ページ読み込み時に設定を取得（init.jsからawait可能にするためPromiseを保持）
var _configReady = loadAppConfig();

// ── ロック状態の適用 ─────────────────────────────
function applyLockState() {
  if (!_configCache) return;
  const categories = _configCache.categories || [];
  const btn = document.getElementById('lockBtn');

  // ボタン表示切替（鍵アイコン）
  const lockedSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>';
  const unlockedSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 5-5 5 5 0 0 1 5 5"></path></svg>';
  if (_isLocked) {
    btn.innerHTML = lockedSvg;
    btn.className = 'locked';
    btn.title = 'ロック';
  } else {
    btn.innerHTML = unlockedSvg;
    btn.className = 'unlocked';
    btn.title = 'アンロック';
  }
  // モバイルメニューのロックボタンも同期
  if (typeof updateMobMenuLock === 'function') updateMobMenuLock();

  // プロジェクト選択リストの表示/非表示（ロック中は非表示）
  const projSelGroup = document.getElementById('workspaceProjectSelect').closest('.header-select-group');
  if (projSelGroup) {
    projSelGroup.style.display = _isLocked ? 'none' : 'flex';
  }

  // カテゴリセレクト再構築（ロック時はlocked項目を除外）
  const catSel = document.getElementById('categorySelect');
  const currentCat = catSel.value;
  catSel.innerHTML = '';
  categories.forEach(c => {
    if (_isLocked && c.locked) return;
    const opt = document.createElement('option');
    opt.value = c.system_id;
    opt.textContent = c.name;
    if (c.system_id === 'it') opt.selected = true;
    catSel.appendChild(opt);
  });
  // 以前の選択値を復元（存在する場合）
  if ([...catSel.options].some(o => o.value === currentCat)) {
    catSel.value = currentCat;
  }

  // アップロードカテゴリセレクト再構築
  const upCatSel = document.getElementById('uploadCategorySelect');
  if (upCatSel) {
    const currentUpCat = upCatSel.value;
    upCatSel.innerHTML = '';
    categories.forEach(c => {
      if (_isLocked && c.locked) return;
      const opt = document.createElement('option');
      opt.value = c.system_id;
      opt.textContent = c.name;
      upCatSel.appendChild(opt);
    });
    if ([...upCatSel.options].some(o => o.value === currentUpCat)) {
      upCatSel.value = currentUpCat;
    }
  }

  // プロジェクトフィルタを再描画（セッション一覧より先に実行し、フィルタ値を確定させる）
  if (typeof renderProjectFilter === 'function') {
    renderProjectFilter();
  }

  // セッション一覧を再描画（ロック対象カテゴリのセッションを除外）
  if (typeof _allSessions !== 'undefined') {
    renderSessionList(_allSessions);
  }

  // ロック復帰時: シークレットプロジェクトの内容が表示されたままにならないよう
  // メインエリアを「新しい会話」と同じ初期状態にリセットする
  if (_isLocked) {
    _sessionId = generateUUID();
    _sequence = 0;
    _sessionCreated = false;
    _sessionCategory = '';
    _conversationHistory = [];
    _viewingHistory = false;
    _viewingSessionId = null;
    clearAttachments();
    document.getElementById('readonlyBanner').classList.remove('visible');
    document.getElementById('inputArea').classList.remove('disabled');
    document.getElementById('chat').innerHTML = '<div class="state" id="emptyState">質問を入力して送信してください。</div>';
    updateActiveSession('');
  }
}

function toggleLock() {
  if (_isLocked) {
    // 解除ボタン押下 → パスワード認証
    openLockPwDialog();
  } else {
    // ロックボタン押下 → 即座にロック状態へ
    _isLocked = true;
    applyLockState();
  }
}

function openLockPwDialog() {
  document.getElementById('pwInput').value = '';
  document.getElementById('pwError').textContent = '';
  document.getElementById('pwOverlay').classList.add('active');
  // パスワードダイアログのOKハンドラを一時的にロック解除用に差し替え
  document.getElementById('pwOverlay').dataset.mode = 'unlock';
  setTimeout(() => document.getElementById('pwInput').focus(), 100);
}

function onTeamChange() {
  const teamMode = document.getElementById('teamSelect').value;
  const defaultModel = _TEAM_DEFAULT_MODELS[teamMode];
  if (defaultModel) {
    document.getElementById('modelSelect').value = defaultModel;
  }
  const targetCategory = _TEAM_CATEGORY_MAP[teamMode];
  if (targetCategory !== undefined && targetCategory !== '') {
    document.getElementById('categorySelect').value = targetCategory;
  }
}

function onWorkspaceProjectChange() {
  const projId = document.getElementById('workspaceProjectSelect').value;
  if (!projId || !_configCache) return;
  const projects = _configCache.workspace_projects || [];
  const proj = projects.find(p => p.id === projId);
  if (!proj) return;
  // チームを自動設定
  if (proj.default_team) {
    document.getElementById('teamSelect').value = proj.default_team;
    onTeamChange();
  }
  // カテゴリを自動設定
  if (proj.default_category) {
    document.getElementById('categorySelect').value = proj.default_category;
  }
  updateWorkspaceCwdHint();
}

// ── パスワードダイアログ ───────────────────────────
function openPwDialog() {
  document.getElementById('pwInput').value = '';
  document.getElementById('pwError').textContent = '';
  document.getElementById('pwOverlay').dataset.mode = 'ingest';
  document.getElementById('pwOverlay').classList.add('active');
  setTimeout(() => document.getElementById('pwInput').focus(), 100);
}

function closePwDialog() {
  document.getElementById('pwOverlay').classList.remove('active');
}

async function submitPwDialog() {
  const pw = document.getElementById('pwInput').value;
  if (!pw) {
    document.getElementById('pwError').textContent = 'パスワードを入力してください';
    return;
  }
  const mode = document.getElementById('pwOverlay').dataset.mode || 'ingest';
  try {
    const res = await fetch('/api/verify-ingest-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw }),
    });
    const data = await res.json();
    if (data.ok) {
      closePwDialog();
      if (mode === 'unlock') {
        _isLocked = false;
        applyLockState();
      } else if (mode === 'colstats') {
        _colStatsUnlocked = true;
        openColStats();
      } else {
        doToggleLogView();
      }
    } else {
      document.getElementById('pwError').textContent = data.error || 'パスワードが違います';
    }
  } catch (e) {
    document.getElementById('pwError').textContent = '通信エラーが発生しました';
  }
}

// Enter キーでパスワード送信
document.getElementById('pwInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); submitPwDialog(); }
});

function onAiServiceChange() {
  const el = document.getElementById('aiServiceSelect');
  if (!el) return;
  try {
    localStorage.setItem('ka_ai_service', el.value);
  } catch (e) { /* ignore */ }
  updateWorkspaceCwdHint();
}
