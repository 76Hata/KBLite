// title.js — タイトル抽出・表示・編集

function extractTitle(text) {
  const m = text.match(/<!--\s*KB_TITLE:\s*([\s\S]+?)\s*-->/);
  return m ? m[1].trim() : null;
}

function stripTitleTag(text) {
  return text.replace(/<!--\s*KB_TITLE:\s*[\s\S]+?\s*-->/g, '').trimEnd();
}

function extractSummary(text) {
  const m = text.match(/<!--\s*KB_TURN_SUMMARY\s*\n([\s\S]+?)\s*-->/);
  return m ? m[1].trim() : null;
}

function stripSummaryTag(text) {
  return text.replace(/<!--\s*KB_TURN_SUMMARY\s*\n[\s\S]+?\s*-->/g, '').trimEnd();
}

function buildTitleHtml(title, sessionId, sequence) {
  if (!title) return '';
  let idSuffix = '';
  if (sessionId) {
    const seq = (sequence != null) ? '-' + sequence : '';
    const fullId = sessionId + seq;
    const shortId = sessionId.slice(0, 12) + seq;
    idSuffix = ' <code class="conv-id">' + esc(shortId) + '</code>'
      + '<button class="conv-id-copy" title="IDをコピー" onclick="event.stopPropagation(); copyConvId(this, \'' + esc(fullId) + '\')">&#x2398;</button>';
  }
  return '<h2 class="response-title">' + _TITLE_ICON_SVG + '<span>' + esc(title) + idSuffix + '</span></h2>';
}

function copyConvId(btn, id) {
  function onSuccess() {
    btn.classList.add('copied');
    btn.innerHTML = '&#x2713;';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = '&#x2398;';
    }, 1500);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(id).then(onSuccess).catch(() => {
      copyViaExecCommand(id, btn, onSuccess);
    });
  } else {
    copyViaExecCommand(id, btn, onSuccess);
  }
}

// ── タイトル編集 ──────────────────────────────────
function createTitleEditBtn(convId, titleEl) {
  const btn = document.createElement('button');
  btn.className = 'title-edit-btn';
  btn.title = 'タイトルを編集';
  btn.innerHTML = '&#x270E;';  // ✎
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const span = titleEl.querySelector('span');
    if (!span) return;
    // conv-id部分を除いたテキストを取得
    const codeEl = span.querySelector('.conv-id');
    const currentTitle = codeEl ? span.textContent.replace(codeEl.textContent, '').trim() : span.textContent.trim();
    const newTitle = prompt('タイトルを編集:', currentTitle);
    if (!newTitle || newTitle.trim() === '' || newTitle.trim() === currentTitle) return;
    updateConvTitle(convId, newTitle.trim(), titleEl);
  });
  return btn;
}

async function updateConvTitle(convId, title, titleEl) {
  try {
    const res = await fetch('/api/conversations/title', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conv_id: convId, title }),
    });
    if (!res.ok) throw new Error('タイトル更新に失敗');
    // 表示を更新
    const span = titleEl.querySelector('span');
    if (span) {
      const codeEl = span.querySelector('.conv-id');
      const idHtml = codeEl ? ' ' + codeEl.outerHTML : '';
      span.innerHTML = esc(title) + idHtml;
    }
    showToast('タイトルを更新しました');
  } catch (e) {
    console.error('会話タイトル更新エラー:', e);
    showToast('タイトルの更新に失敗しました');
  }
}

async function editConvTitle(convId, placeholderEl, sessionId, sequence) {
  const newTitle = prompt('タイトルを入力してください:');
  if (!newTitle || newTitle.trim() === '') return;
  try {
    const res = await fetch('/api/conversations/title', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conv_id: convId, title: newTitle.trim() }),
    });
    if (!res.ok) throw new Error('タイトル更新に失敗');
    // プレースホルダをタイトルに置換
    const titleHtml = buildTitleHtml(newTitle.trim(), sessionId, sequence);
    const temp = document.createElement('div');
    temp.innerHTML = titleHtml;
    const titleEl = temp.firstChild;
    titleEl.appendChild(createTitleEditBtn(convId, titleEl));
    placeholderEl.replaceWith(titleEl);
    showToast('タイトルを追加しました');
  } catch (e) {
    console.error('会話タイトル更新エラー:', e);
    showToast('タイトルの更新に失敗しました');
  }
}
