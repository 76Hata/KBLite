// tasks.js — タスク管理パネル UI

// ── 状態 ───────────────────────────────────────────
let _taskPanelOpen = false;
let _editingTaskId = null;   // フォームで編集中のタスクID（null = 新規）
let _expandedTaskId = null;  // 詳細展開中のタスクID
let _selectedTaskIds = new Set(); // チェックボックス選択中のタスクID
let _visibleTaskIds = [];          // 現在表示中のタスクID一覧（全選択用）

// ── パネル開閉 ────────────────────────────────────
function toggleTaskPanel() {
  _taskPanelOpen ? closeTaskPanel() : openTaskPanel();
}

function openTaskPanel() {
  _taskPanelOpen = true;
  document.getElementById('taskPanel').classList.add('open');
  document.getElementById('taskPanelOverlay').classList.add('visible');
  document.getElementById('taskPanelToggleBtn').classList.add('active');
  loadTasks();
}

function closeTaskPanel() {
  _taskPanelOpen = false;
  document.getElementById('taskPanel').classList.remove('open');
  document.getElementById('taskPanelOverlay').classList.remove('visible');
  document.getElementById('taskPanelToggleBtn').classList.remove('active');
  closeTaskForm();
}

// ── タスク一覧取得 ────────────────────────────────
async function loadTasks() {
  const statusFilter = document.getElementById('taskStatusFilter').value;
  const scopeFilter = document.getElementById('taskScopeFilter')?.value || '';
  const qs = new URLSearchParams();
  if (statusFilter) qs.set('status', statusFilter);
  if (scopeFilter) qs.set('scope', scopeFilter);
  const params = qs.toString() ? `?${qs.toString()}` : '';
  try {
    const res = await fetch(`/api/tasks${params}`);
    const data = await res.json();
    renderTaskList(data.tasks || []);
    // バッジは scope フィルタに関係なく大きな案件のみで集計
    updateTaskBadgeFromApi();
  } catch (e) {
    document.getElementById('taskList').innerHTML =
      '<div class="task-empty">読み込みエラー</div>';
  }
}

async function updateTaskBadgeFromApi() {
  try {
    const res = await fetch('/api/tasks?scope=global');
    const d = await res.json();
    updateTaskBadge(d.tasks || []);
  } catch (_) {}
}

function updateTaskBadge(tasks) {
  const active = tasks.filter(t => t.status === 'in_progress' || t.status === 'todo').length;
  const badge = document.getElementById('taskBadge');
  if (active > 0) {
    badge.textContent = active > 99 ? '99+' : String(active);
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }
}

// ── 一覧レンダリング ──────────────────────────────
function renderTaskList(tasks) {
  _visibleTaskIds = tasks.map(t => String(t.id));
  const el = document.getElementById('taskList');
  if (tasks.length === 0) {
    el.innerHTML = '<div class="task-empty">タスクはありません</div>';
    updateBulkBar();
    return;
  }
  el.innerHTML = tasks.map(t => renderTaskItem(t)).join('');
  updateBulkBar();
}

function renderTaskItem(t) {
  const isExpanded = _expandedTaskId === t.id;
  const isSelected = _selectedTaskIds.has(String(t.id));
  const priorityLabel = { high: '★ 高', normal: '中', low: '▽ 低' }[t.priority] || t.priority;
  const notesHtml = (t.notes || []).map(n => {
    const time = (n.created_at || '').replace('T', ' ').slice(0, 16);
    return `<div class="task-note-item"><span class="task-note-time">${_esc(time)}</span>${_esc(n.note)}</div>`;
  }).join('');

  const dueHtml = t.due_date
    ? `<span class="task-due-badge${_isOverdue(t) ? ' overdue' : ''}">${_esc(t.due_date)}</span>`
    : '';
  const notesCountHtml = (t.notes || []).length > 0
    ? `<span class="task-notes-count">${t.notes.length}件のメモ</span>`
    : '';

  const source = t.source || 'manual';
  const scope = t.scope || 'global';
  const sourceLabel = { todowrite: 'TodoWrite', manual: '手動', mcp: 'MCP' }[source] || source;
  const scopeLabel = { session: 'セッション', global: '大案件' }[scope] || scope;
  const sourceHtml = `<span class="task-source-badge ${_esc(source)}" title="出どころ">${_esc(sourceLabel)}</span>`;
  const scopeHtml = `<span class="task-scope-badge ${_esc(scope)}" title="スコープ">${_esc(scopeLabel)}</span>`;

  const statusActions = _statusActions(t);

  return `<div class="task-item ${t.status}${isExpanded ? ' expanded' : ''}${isSelected ? ' selected' : ''}" id="task-${_esc(t.id)}" onclick="toggleTaskExpand(event,'${_esc(t.id)}')">
  <div class="task-item-header">
    <input type="checkbox" class="task-checkbox" ${isSelected ? 'checked' : ''} onclick="toggleTaskSelect(event,'${_esc(t.id)}')" title="選択">
    <span class="task-status-dot ${t.status}"></span>
    <span class="task-item-title">${_esc(t.title)}</span>
  </div>
  <div class="task-item-meta">
    <span class="task-priority-badge ${t.priority}">${_esc(priorityLabel)}</span>
    ${scopeHtml}
    ${sourceHtml}
    ${dueHtml}
    ${notesCountHtml}
  </div>
  <div class="task-detail">
    ${t.description ? `<div class="task-desc">${_esc(t.description)}</div>` : ''}
    ${notesHtml ? `<div class="task-note-list">${notesHtml}</div>` : ''}
    <div class="task-note-input-wrap" id="noteWrap-${_esc(t.id)}">
      <textarea class="task-note-input" id="noteInput-${_esc(t.id)}" placeholder="メモを追加..." rows="2"></textarea>
      <button class="task-note-submit" onclick="submitNote(event,'${_esc(t.id)}')">追加</button>
    </div>
    <div class="task-detail-actions">
      ${statusActions}
      <button class="task-action-btn" onclick="addNoteToggle(event,'${_esc(t.id)}')">メモ追加</button>
      <button class="task-action-btn" onclick="openTaskFormEdit(event,'${_esc(t.id)}','${_esc(t.title)}','${_esc(t.description||'')}','${t.priority}','${t.due_date||''}')">編集</button>
      <button class="task-action-btn danger" onclick="deleteTask(event,'${_esc(t.id)}')">削除</button>
    </div>
  </div>
</div>`;
}

function _statusActions(t) {
  const btns = [];
  if (t.status === 'todo') {
    btns.push(`<button class="task-action-btn" onclick="changeStatus(event,'${t.id}','in_progress')">開始</button>`);
    btns.push(`<button class="task-action-btn" onclick="changeStatus(event,'${t.id}','cancelled')">キャンセル</button>`);
  }
  if (t.status === 'in_progress') {
    btns.push(`<button class="task-action-btn" onclick="changeStatus(event,'${t.id}','done')">完了</button>`);
    btns.push(`<button class="task-action-btn" onclick="changeStatus(event,'${t.id}','todo')">保留</button>`);
  }
  if (t.status === 'done' || t.status === 'cancelled') {
    btns.push(`<button class="task-action-btn" onclick="changeStatus(event,'${t.id}','todo')">再開</button>`);
  }
  return btns.join('');
}

function _isOverdue(t) {
  if (!t.due_date || t.status === 'done' || t.status === 'cancelled') return false;
  return new Date(t.due_date) < new Date();
}

// ── タスク展開 ────────────────────────────────────
function toggleTaskExpand(e, taskId) {
  // ボタンクリックは伝播しているが、action ボタン類は stopPropagation 済み
  _expandedTaskId = _expandedTaskId === taskId ? null : taskId;
  // パネルを再描画せず DOM を直接切り替え（チラつき防止）
  document.querySelectorAll('.task-item').forEach(el => {
    const id = el.id.replace('task-', '');
    el.classList.toggle('expanded', id === _expandedTaskId);
  });
}

// ── ステータス変更 ────────────────────────────────
const _statusLabel = { todo: '未着手', in_progress: '進行中', done: '完了', cancelled: 'キャンセル' };

async function changeStatus(e, taskId, newStatus) {
  e.stopPropagation();
  const label = _statusLabel[newStatus] || newStatus;
  if (!confirm(`ステータスを「${label}」に変更しますか？`)) return;
  try {
    await fetch(`/api/tasks/${taskId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    await loadTasks();
    _expandedTaskId = taskId; // 変更後も展開状態を維持
    // 再 render 後に展開フラグを適用
    document.querySelectorAll('.task-item').forEach(el => {
      el.classList.toggle('expanded', el.id === `task-${taskId}`);
    });
  } catch (err) {
    alert('ステータス更新に失敗しました');
  }
}

// ── ノート追加 ────────────────────────────────────
function addNoteToggle(e, taskId) {
  e.stopPropagation();
  const wrap = document.getElementById(`noteWrap-${taskId}`);
  if (wrap) {
    wrap.classList.toggle('visible');
    if (wrap.classList.contains('visible')) {
      document.getElementById(`noteInput-${taskId}`)?.focus();
    }
  }
}

async function submitNote(e, taskId) {
  e.stopPropagation();
  const input = document.getElementById(`noteInput-${taskId}`);
  const note = (input?.value || '').trim();
  if (!note) return;
  try {
    await fetch(`/api/tasks/${taskId}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    });
    await loadTasks();
    _expandedTaskId = taskId;
    document.querySelectorAll('.task-item').forEach(el => {
      el.classList.toggle('expanded', el.id === `task-${taskId}`);
    });
  } catch (err) {
    alert('メモ追加に失敗しました');
  }
}

// ── タスク削除 ────────────────────────────────────
async function deleteTask(e, taskId) {
  e.stopPropagation();
  if (!confirm('このタスクを削除しますか？')) return;
  try {
    await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    if (_expandedTaskId === taskId) _expandedTaskId = null;
    await loadTasks();
  } catch (err) {
    alert('削除に失敗しました');
  }
}

// ── タスク追加/編集フォーム ────────────────────────
function openTaskForm() {
  _editingTaskId = null;
  document.getElementById('taskFormId').value = '';
  document.getElementById('taskFormTitle').value = '';
  document.getElementById('taskFormDesc').value = '';
  document.getElementById('taskFormPriority').value = 'normal';
  document.getElementById('taskFormDue').value = '';
  document.getElementById('taskForm').style.display = 'block';
  document.getElementById('taskFormTitle').focus();
}

function openTaskFormEdit(e, taskId, title, desc, priority, dueDate) {
  e.stopPropagation();
  _editingTaskId = taskId;
  document.getElementById('taskFormId').value = taskId;
  document.getElementById('taskFormTitle').value = title;
  document.getElementById('taskFormDesc').value = desc;
  document.getElementById('taskFormPriority').value = priority || 'normal';
  document.getElementById('taskFormDue').value = dueDate || '';
  document.getElementById('taskForm').style.display = 'block';
  document.getElementById('taskFormTitle').focus();
}

function closeTaskForm() {
  _editingTaskId = null;
  document.getElementById('taskForm').style.display = 'none';
}

async function saveTaskForm() {
  const title = document.getElementById('taskFormTitle').value.trim();
  if (!title) {
    alert('タイトルを入力してください');
    return;
  }
  const body = {
    title,
    description: document.getElementById('taskFormDesc').value.trim(),
    priority: document.getElementById('taskFormPriority').value,
    due_date: document.getElementById('taskFormDue').value || null,
  };

  try {
    if (_editingTaskId) {
      await fetch(`/api/tasks/${_editingTaskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } else {
      await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }
    closeTaskForm();
    await loadTasks();
  } catch (err) {
    alert('保存に失敗しました');
  }
}

// ── チェックボックス選択削除 ──────────────────────
function toggleTaskSelect(e, taskId) {
  e.stopPropagation();
  const id = String(taskId);
  if (_selectedTaskIds.has(id)) {
    _selectedTaskIds.delete(id);
  } else {
    _selectedTaskIds.add(id);
  }
  const el = document.getElementById(`task-${id}`);
  if (el) el.classList.toggle('selected', _selectedTaskIds.has(id));
  updateBulkBar();
}

function updateBulkBar() {
  const bar = document.getElementById('taskBulkBar');
  if (!bar) return;
  const count = _selectedTaskIds.size;
  bar.style.display = count > 0 ? 'flex' : 'none';
  const countEl = bar.querySelector('.task-bulk-count');
  if (countEl) countEl.textContent = `${count}件選択中`;
  const selectAllBtn = document.getElementById('taskSelectAllBtn');
  if (selectAllBtn) {
    const allSelected = _visibleTaskIds.length > 0 &&
      _visibleTaskIds.every(id => _selectedTaskIds.has(id));
    selectAllBtn.textContent = allSelected ? '全解除' : '全選択';
  }
}

async function deleteSelectedTasks() {
  const count = _selectedTaskIds.size;
  if (count === 0) return;
  if (!confirm(`選択した${count}件のタスクを削除しますか？`)) return;
  const ids = Array.from(_selectedTaskIds);
  try {
    await Promise.all(ids.map(id => fetch(`/api/tasks/${id}`, { method: 'DELETE' })));
    if (ids.includes(String(_expandedTaskId))) _expandedTaskId = null;
    _selectedTaskIds.clear();
    await loadTasks();
  } catch (err) {
    alert('削除に失敗しました');
  }
}

function clearTaskSelection() {
  _selectedTaskIds.clear();
  document.querySelectorAll('.task-item.selected').forEach(el => el.classList.remove('selected'));
  document.querySelectorAll('.task-checkbox').forEach(cb => { cb.checked = false; });
  updateBulkBar();
}

function selectAllTasks() {
  const allSelected = _visibleTaskIds.length > 0 &&
    _visibleTaskIds.every(id => _selectedTaskIds.has(id));
  if (allSelected) {
    clearTaskSelection();
  } else {
    _visibleTaskIds.forEach(id => _selectedTaskIds.add(id));
    document.querySelectorAll('.task-item').forEach(el => el.classList.add('selected'));
    document.querySelectorAll('.task-checkbox').forEach(cb => { cb.checked = true; });
    updateBulkBar();
  }
}

// ── ユーティリティ ────────────────────────────────
function _esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── 初期化（バッジ用に未完了件数だけ取得 — 大きな案件のみ） ────────
async function initTaskBadge() {
  try {
    const res = await fetch('/api/tasks?scope=global');
    const d = await res.json();
    updateTaskBadge(d.tasks || []);
  } catch (_) {}
}
