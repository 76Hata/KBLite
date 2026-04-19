// project.js — プロジェクト管理・セッション名変更・セッション移動

async function loadProjects() {
  try {
    const res = await fetch('/api/projects');
    const data = await res.json();
    _projects = data.projects || [];
    renderProjectFilter();
  } catch (e) {
    console.error('プロジェクト一覧エラー:', e);
  }
}

function renderProjectFilter() {
  const sel = document.getElementById('projectFilter');
  const current = sel.value;
  let html = '<option value="">すべての会話</option><option value="__bookmarked__">ブックマーク</option><option value="__unassigned__">未分類</option>';
  for (const p of _projects) {
    // ロック中はロック対象カテゴリの名前またはsystem_idと一致するプロジェクトを非表示
    if (_isLocked && (_LOCKED_CATEGORY_NAMES.has(p.name) || _LOCKED_CATEGORIES.has(p.name))) continue;
    html += '<option value="' + esc(p.id || p.project_id) + '">' + esc(p.name) + '</option>';
  }
  sel.innerHTML = html;
  // 以前の選択値がオプションに存在する場合のみ復元、なければ「すべての会話」にリセット
  if ([...sel.options].some(o => o.value === current)) {
    sel.value = current;
  } else {
    sel.value = '';
  }
}

function onProjectFilterChange() {
  loadSessions(0);
}

async function promptCreateProject() {
  const name = prompt('新しいプロジェクト名を入力してください:');
  if (!name || !name.trim()) return;
  try {
    const res = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (res.ok) {
      showToast('プロジェクト「' + name.trim() + '」を作成しました');
      await loadProjects();
    } else {
      showToast('プロジェクト作成に失敗しました');
    }
  } catch (e) {
    showToast('プロジェクト作成に失敗しました');
  }
}

async function promptRenameProject() {
  const sel = document.getElementById('projectFilter');
  const pid = sel.value;
  if (!pid || pid === '__unassigned__') {
    showToast('名前変更するプロジェクトを選択してください');
    return;
  }
  const proj = _projects.find(p => (p.id || p.project_id) === pid);
  const newName = prompt('新しいプロジェクト名:', proj ? proj.name : '');
  if (!newName || !newName.trim()) return;
  try {
    const res = await fetch('/api/projects/' + encodeURIComponent(pid), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim() }),
    });
    if (res.ok) {
      showToast('プロジェクト名を変更しました');
      await loadProjects();
    }
  } catch (e) {
    showToast('プロジェクト名変更に失敗しました');
  }
}

async function promptDeleteProject() {
  const sel = document.getElementById('projectFilter');
  const pid = sel.value;
  if (!pid || pid === '__unassigned__') {
    showToast('削除するプロジェクトを選択してください');
    return;
  }
  const proj = _projects.find(p => (p.id || p.project_id) === pid);
  if (!confirm('プロジェクト「' + (proj ? proj.name : pid) + '」を削除しますか？\n（会話は削除されず未分類に戻ります）')) return;
  try {
    const res = await fetch('/api/projects/' + encodeURIComponent(pid), { method: 'DELETE' });
    if (res.ok) {
      showToast('プロジェクトを削除しました');
      sel.value = '';
      await loadProjects();
      await loadSessions();
    }
  } catch (e) {
    showToast('プロジェクト削除に失敗しました');
  }
}

async function promptRenameSession(sessionId) {
  // メニューを閉じる
  document.querySelectorAll('.session-menu.open').forEach(m => m.classList.remove('open'));

  // 現在のタイトルを取得
  const item = document.querySelector(`.session-item[data-session-id="${sessionId}"]`);
  const currentTitle = item ? item.querySelector('.session-item-title').textContent.trim() : '';
  const newTitle = prompt('新しいタイトルを入力してください:', currentTitle);
  if (!newTitle || newTitle.trim() === '' || newTitle.trim() === currentTitle) return;

  try {
    const res = await fetch('/api/sessions/' + encodeURIComponent(sessionId) + '/title', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle.trim() }),
    });
    if (!res.ok) throw new Error('タイトル更新に失敗');
    showToast('タイトルを更新しました');
    loadSessions();
  } catch (e) {
    console.error('セッション名変更エラー:', e);
    showToast('タイトルの更新に失敗しました');
  }
}

async function promptMoveSession(sessionId) {
  // メニューを閉じる
  document.querySelectorAll('.session-menu.open').forEach(m => m.classList.remove('open'));

  if (_projects.length === 0) {
    const create = confirm('プロジェクトがありません。新しく作成しますか？');
    if (create) {
      await promptCreateProject();
      if (_projects.length === 0) return;
    } else {
      return;
    }
  }

  // プロジェクト選択ダイアログ（トグルボタン方式）
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
  const dialog = document.createElement('div');
  dialog.style.cssText = 'background:#2a2a2a;border-radius:10px;padding:20px;min-width:280px;max-width:400px;color:#eee;';
  dialog.innerHTML = '<div style="font-size:14px;font-weight:600;margin-bottom:12px;">移動先プロジェクト</div>';

  const btnContainer = document.createElement('div');
  btnContainer.style.cssText = 'display:flex;flex-direction:column;gap:6px;max-height:300px;overflow-y:auto;';

  // 「未分類に戻す」ボタン
  const noneBtn = document.createElement('button');
  noneBtn.textContent = '未分類に戻す';
  noneBtn.style.cssText = 'padding:8px 12px;border:1px solid #555;background:#333;color:#ccc;border-radius:6px;cursor:pointer;text-align:left;font-size:13px;';
  noneBtn.onmouseenter = () => { noneBtn.style.background = '#444'; };
  noneBtn.onmouseleave = () => { noneBtn.style.background = '#333'; };
  noneBtn.onclick = () => { overlay.remove(); doMoveSession(sessionId, ''); };
  btnContainer.appendChild(noneBtn);

  // プロジェクトボタン（ロック中はロック対象カテゴリの名前/system_idと一致するプロジェクトを除外）
  _projects.forEach(p => {
    if (_isLocked && (_LOCKED_CATEGORY_NAMES.has(p.name) || _LOCKED_CATEGORIES.has(p.name))) return;
    const btn = document.createElement('button');
    btn.textContent = p.name;
    btn.style.cssText = 'padding:8px 12px;border:1px solid #555;background:#333;color:#eee;border-radius:6px;cursor:pointer;text-align:left;font-size:13px;';
    btn.onmouseenter = () => { btn.style.background = '#444'; };
    btn.onmouseleave = () => { btn.style.background = '#333'; };
    btn.onclick = () => { overlay.remove(); doMoveSession(sessionId, p.id || p.project_id); };
    btnContainer.appendChild(btn);
  });

  dialog.appendChild(btnContainer);

  // キャンセルボタン
  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'キャンセル';
  cancelBtn.style.cssText = 'margin-top:12px;padding:6px 12px;border:none;background:transparent;color:#888;cursor:pointer;font-size:12px;width:100%;';
  cancelBtn.onclick = () => overlay.remove();
  dialog.appendChild(cancelBtn);

  overlay.appendChild(dialog);
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
}

async function doMoveSession(sessionId, targetId) {
  try {
    const res = await fetch('/api/sessions/move', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, project_id: targetId }),
    });
    if (res.ok) {
      showToast(targetId ? 'プロジェクトに移動しました' : '未分類に戻しました');
      await loadSessions();
    }
  } catch (e) {
    showToast('移動に失敗しました');
  }
}
