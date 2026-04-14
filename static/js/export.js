// export.js — コピー・ダウンロード・PDF出力・メッセージアクションボタン

// ── メッセージアクションボタンの生成 ───────────────
function createMsgActions() {
  const actions = document.createElement('div');
  actions.className = 'msg-actions';

  // コピーボタン
  const copyBtn = document.createElement('button');
  copyBtn.className = 'msg-action-btn';
  copyBtn.setAttribute('title', 'Markdownをコピー');
  copyBtn.setAttribute('aria-label', '回答をMarkdown形式でコピー');
  copyBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  copyBtn.addEventListener('click', function() { copyAnswer(this); });

  // ダウンロードボタン（Markdown）
  const dlBtn = document.createElement('button');
  dlBtn.className = 'msg-action-btn';
  dlBtn.setAttribute('title', 'Markdownをダウンロード');
  dlBtn.setAttribute('aria-label', '回答をMarkdownファイルとしてダウンロード');
  dlBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>';
  dlBtn.addEventListener('click', function() { downloadAnswer(this); });

  // PDFダウンロードボタン
  const pdfBtn = document.createElement('button');
  pdfBtn.className = 'msg-action-btn';
  pdfBtn.setAttribute('title', 'PDFをダウンロード');
  pdfBtn.setAttribute('aria-label', '回答をPDFとしてダウンロード');
  pdfBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="9" y1="15" x2="15" y2="15"></line><line x1="9" y1="11" x2="13" y2="11"></line></svg>';
  pdfBtn.addEventListener('click', function() { downloadPdf(this); });

  // 編集ボタン
  const editBtn = document.createElement('button');
  editBtn.className = 'msg-action-btn';
  editBtn.setAttribute('title', '回答を編集');
  editBtn.setAttribute('aria-label', '回答テキストを編集');
  editBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>';
  editBtn.addEventListener('click', function() { openConvEdit(this.closest('.msg.assistant')); });

  // 分岐ボタン
  const forkBtn = document.createElement('button');
  forkBtn.className = 'msg-action-btn';
  forkBtn.setAttribute('title', '新しい会話に分岐');
  forkBtn.setAttribute('aria-label', 'この会話を分岐して新しい会話を開始');
  forkBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><line x1="6" y1="15" x2="6" y2="9"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>';
  forkBtn.addEventListener('click', function() { forkSession(); });

  actions.appendChild(forkBtn);
  actions.appendChild(copyBtn);
  actions.appendChild(dlBtn);
  actions.appendChild(pdfBtn);
  actions.appendChild(editBtn);
  return actions;
}

// ── 回答編集UI ──────────────────────────────────────
function openConvEdit(msgDiv) {
  if (!msgDiv) return;
  const convId = msgDiv.getAttribute('data-conv-id');
  if (!convId) {
    showToast('この回答はまだ保存されていないため編集できません');
    return;
  }

  const existing = msgDiv.querySelector('.conv-edit-area');
  if (existing) { existing.remove(); return; }

  const rawMd = msgDiv.getAttribute('data-raw-markdown') || '';

  const wrap = document.createElement('div');
  wrap.className = 'conv-edit-area';

  const textarea = document.createElement('textarea');
  textarea.className = 'conv-edit-textarea';
  textarea.value = rawMd;

  const btnRow = document.createElement('div');
  btnRow.className = 'conv-edit-btn-row';

  const saveBtn = document.createElement('button');
  saveBtn.className = 'conv-edit-save';
  saveBtn.textContent = '保存';
  saveBtn.addEventListener('click', async () => {
    const newAnswer = textarea.value;
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中...';
    try {
      const res = await fetch('/api/conversations/' + encodeURIComponent(convId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: newAnswer }),
      });
      if (!res.ok) throw new Error('保存失敗');
      // UI更新
      msgDiv.setAttribute('data-raw-markdown', newAnswer);
      const mc = msgDiv.querySelector('.msg-content');
      if (mc) {
        // タイトル部分を保持しつつ、回答部分のみ差し替え
        const titleEl = mc.querySelector('.response-title');
        const titleHtml = titleEl ? titleEl.outerHTML : '';
        mc.innerHTML = titleHtml + mdToHtml(newAnswer);
        await renderMermaidBlocks(mc);
        await renderDrawioBlocks(mc);
        addCodeBlockButtons(mc);
      }
      wrap.remove();
      showToast('保存しました');
    } catch (e) {
      saveBtn.disabled = false;
      saveBtn.textContent = '保存';
      showToast('保存に失敗しました');
    }
  });

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'conv-edit-cancel';
  cancelBtn.textContent = 'キャンセル';
  cancelBtn.addEventListener('click', () => wrap.remove());

  btnRow.appendChild(saveBtn);
  btnRow.appendChild(cancelBtn);
  wrap.appendChild(textarea);
  wrap.appendChild(btnRow);
  msgDiv.appendChild(wrap);
  textarea.focus();
}

// ── コピー機能 ──────────────────────────────────────
function copyAnswer(btn) {
  const msgDiv = btn.closest('.msg.assistant');
  if (!msgDiv) return;

  const markdown = buildMarkdownContent(msgDiv);

  // Clipboard API を試す
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(markdown).then(() => {
      showCopySuccess(btn);
    }).catch(() => {
      // Clipboard API 失敗時のフォールバック
      copyViaExecCommand(markdown, btn);
    });
  } else {
    // Clipboard API が利用不可の場合
    copyViaExecCommand(markdown, btn);
  }
}

// ── ユーザーメッセージ用コピーボタン ─────────────────
const _copySvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
const _checkSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

function _createUserCopyBtn() {
  const wrap = document.createElement('div');
  wrap.className = 'user-msg-actions';
  const btn = document.createElement('button');
  btn.className = 'msg-action-btn user-copy-btn';
  btn.title = 'プロンプトをコピー';
  btn.innerHTML = _copySvg;
  btn.addEventListener('click', function() {
    const msgDiv = this.closest('.msg.user');
    if (!msgDiv) return;
    const text = msgDiv.getAttribute('data-raw-text') || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => showCopySuccess(this)).catch(() => copyViaExecCommand(text, this));
    } else {
      copyViaExecCommand(text, this);
    }
  });
  wrap.appendChild(btn);
  return wrap;
}

// 成功フィードバック: アイコンをチェックマークに変更
function showCopySuccess(btn) {
  btn.classList.add('copied');
  btn.innerHTML = _checkSvg;
  showToast('コピーしました');

  setTimeout(() => {
    btn.classList.remove('copied');
    btn.innerHTML = _copySvg;
  }, 2000);
}

// ── ダウンロード機能 ────────────────────────────────
function downloadAnswer(btn) {
  const msgDiv = btn.closest('.msg.assistant');
  if (!msgDiv) return;

  const markdown = buildMarkdownContent(msgDiv);
  const title = msgDiv.getAttribute('data-title');

  // ファイル名の生成
  let filename;
  if (title) {
    // タイトルベース: 記号を除去してファイル名に適した形にする
    filename = title.replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, '_').slice(0, 60) + '.md';
  } else {
    // 日時ベース
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    filename = 'answer_' + now.getFullYear() + pad(now.getMonth() + 1) + pad(now.getDate()) + '_' + pad(now.getHours()) + pad(now.getMinutes()) + pad(now.getSeconds()) + '.md';
  }

  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  showToast('ダウンロードしました');
}

// ── PDF出力 ──────────────────────────────────────────
async function downloadPdf(btn) {
  const msgDiv = btn.closest('.msg.assistant');
  if (!msgDiv) return;

  const question = msgDiv.getAttribute('data-question') || '';
  const rawMd = msgDiv.getAttribute('data-raw-markdown') || '';
  const title = msgDiv.getAttribute('data-title') || '';

  // PDF用HTMLを組み立て（ブラウザ印刷機能で出力するため、完全なHTMLページを構築）
  let html = '';
  if (title) {
    html += '<h1 style="font-size:18px; color:#1e3a5f; border-bottom:2px solid #1e3a5f; padding-bottom:8px; margin-bottom:16px;">' + esc(title) + '</h1>';
  }
  if (question) {
    html += '<h2 style="font-size:14px; color:#555; margin-bottom:4px;">質問</h2>';
    html += '<div style="background:#e3f0ff; border-radius:8px; padding:12px; margin-bottom:16px; font-size:14px;">' + esc(question).replace(/\n/g, '<br>') + '</div>';
  }
  html += '<h2 style="font-size:14px; color:#555; margin-bottom:4px;">回答</h2>';
  html += '<div>' + mdToHtml(rawMd) + '</div>';

  // Mermaid図をレンダリングするため、一時DOMに追加
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  document.body.appendChild(tmp);
  await renderMermaidBlocks(tmp);
  await renderDrawioBlocks(tmp);
  html = tmp.innerHTML;
  document.body.removeChild(tmp);

  // 印刷用の新しいウィンドウを開き、ブラウザネイティブのPDF保存を使用
  // html2canvasのCJK文字幅計算バグを根本回避
  const printWin = window.open('', '_blank');
  if (!printWin) {
    showToast('ポップアップがブロックされました。許可してください。');
    return;
  }
  printWin.document.write('<!DOCTYPE html><html><head><meta charset="utf-8">');
  printWin.document.write('<title>' + esc(title || 'Knowledge Assistant') + '</title>');
  printWin.document.write('<style>');
  printWin.document.write(`
    @page { size: A4; margin: 15mm; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif;
      color: #222; font-size: 13px; line-height: 1.8;
      max-width: 700px; margin: 0 auto; padding: 0;
    }
    h1, h2, h3, h4, h5, h6 { font-weight: 700; margin: 12px 0 6px; }
    h1 { font-size: 18px; } h2 { font-size: 15px; } h3 { font-size: 14px; }
    h4 { font-size: 13.5px; } h5, h6 { font-size: 13px; }
    p { margin-bottom: 6px; }
    pre { background: #f5f5f5; border-radius: 6px; padding: 10px; font-size: 12px;
          white-space: pre-wrap; word-break: break-all; }
    code { font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
    th { background: #f0f0f0; font-weight: 600; }
    img { display: block; margin: 8px auto; max-width: 100%; height: auto; }
    blockquote { border-left: 3px solid #ccc; margin: 8px 0; padding: 4px 12px; color: #555; }
    hr { border: none; border-top: 1px solid #ddd; margin: 12px 0; }
    /* ページ分割制御 */
    h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
    p, li, tr, pre, blockquote, table, img { page-break-inside: avoid; }
  `);
  printWin.document.write('</style></head><body>');
  printWin.document.write(html);
  printWin.document.write('</body></html>');
  printWin.document.close();

  // レンダリング完了を待ってから印刷ダイアログを開く
  printWin.onload = function() {
    setTimeout(function() {
      printWin.print();
    }, 300);
  };
  showToast('印刷ダイアログで「PDFに保存」を選択してください');
}

// ── Markdownコンテンツの組み立て ────────────────────
function buildMarkdownContent(msgDiv) {
  const question = msgDiv.getAttribute('data-question') || '';
  const rawMd = msgDiv.getAttribute('data-raw-markdown') || '';

  let content = '';
  if (question) {
    content += '## 質問\n' + question + '\n\n';
  }
  content += '## 回答\n' + rawMd;
  return content;
}
