// chat.js — チャット送受信・SSE・メッセージ表示・待機インジケーター

// ── メッセージ表示 ─────────────────────────────────
// options: { rawMarkdown, question, rawText } — ボタン付与用
function appendMessage(role, html, isStreaming, options) {
  const empty = document.getElementById('emptyState');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `msg ${role}${isStreaming ? ' typing' : ''}`;

  const inner = document.createElement('div');
  inner.className = 'msg-content';
  inner.innerHTML = html;
  div.appendChild(inner);

  // assistant メッセージにコピー/ダウンロードボタンを追加
  if (role === 'assistant' && !isStreaming && options) {
    if (options.rawMarkdown) {
      div.setAttribute('data-raw-markdown', options.rawMarkdown);
    }
    if (options.question) {
      div.setAttribute('data-question', options.question);
    }
    if (options.title) {
      div.setAttribute('data-title', options.title);
    }
    div.appendChild(createMsgActions());
  }

  // user メッセージにコピーボタンを追加
  if (role === 'user' && options && options.rawText) {
    div.setAttribute('data-raw-text', options.rawText);
    div.appendChild(_createUserCopyBtn());
  }

  document.getElementById('chat').appendChild(div);
  scrollToBottom();
  return div;
}

// ── SSE ストリーム処理（共通） ──────────────────────
function _isCursorServiceValue(value) {
  if (!value) return false;
  const normalized = String(value).trim().toLowerCase();
  return normalized === 'cursor' || normalized === 'cursor agent';
}

function _isCursorServiceActive(evtAiService) {
  const aiSvcEl = document.getElementById('aiServiceSelect');
  return _isCursorServiceValue(evtAiService)
    || _isCursorServiceValue(_activeRequestAiService)
    || _isCursorServiceValue(aiSvcEl && aiSvcEl.value);
}

async function processSSEStream(res, aiContent, aiDiv, onDone, onFirstChunk) {
  const reader = res.body.getReader();
  _currentReader = reader;
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';
  let receivedDone = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const evt = JSON.parse(line.slice(6));
        if (evt.type === 'heartbeat') {
          continue;
        } else if (evt.type === 'task_id') {
          _activeTaskId = evt.task_id;
          const isCursorSvc = _isCursorServiceActive(evt.ai_service);
          if (isCursorSvc) {
            _waitStatusText = 'Cursor で実行中...';
          } else if (evt.routed_model) {
            _waitStatusText = evt.routed_model + ' で実行中...';
          }
        } else if (evt.type === 'chunk') {
          if (onFirstChunk) { onFirstChunk(); onFirstChunk = null; }
          fullText += evt.content;
          aiContent.innerHTML = mdToHtml(fullText);
          scrollToBottom();
        } else if (evt.type === 'done') {
          receivedDone = true;
          _activeTaskId = null;
          aiDiv.classList.remove('typing');
          if (evt.claude_session_id) _claudeSessionId = evt.claude_session_id;
          if (evt.web_search_used) {
            _showWebSearchMemoryBanner(aiDiv, fullText);
          }
          if (onDone) onDone(fullText);
        } else if (evt.type === 'cancelled') {
          receivedDone = true;
          _activeTaskId = null;
          if (onFirstChunk) { onFirstChunk(); onFirstChunk = null; }
          aiDiv.classList.remove('typing');
          if (fullText) {
            aiContent.innerHTML = mdToHtml(fullText) + '<p style="color:#e67e22;font-size:13px;margin-top:8px;">[中止されました]</p>';
          } else {
            aiContent.innerHTML = '<p style="color:#e67e22;">[中止されました]</p>';
          }
        } else if (evt.type === 'waiting') {
          _waitStatusText = _isCursorServiceActive(evt.ai_service)
            ? 'Cursor で処理中...'
            : (evt.message || '順番待ち中...');
        } else if (evt.type === 'tool_activity') {
          _waitStatusText = toolDisplayName(evt.tool) + ' を実行中...';
        } else if (evt.type === 'thinking') {
          _waitStatusText = '思考中...';
        } else if (evt.type === 'error') {
          receivedDone = true;
          _activeTaskId = null;
          if (onFirstChunk) { onFirstChunk(); onFirstChunk = null; }
          aiDiv.classList.remove('typing');
          aiContent.innerHTML = '<p style="color:#c0392b">' + esc(evt.message) + '</p>';
        }
      } catch (_) {}
    }
  }

  // doneイベント未受信でストリームが終了 → SSE切断と判断してポーリング復帰を発動
  if (!receivedDone && _activeTaskId) {
    _currentReader = null;
    console.log('SSEストリームがdoneイベントなしで終了、ポーリング復帰へ: task=' + _activeTaskId);
    throw new Error('SSE_DISCONNECTED');
  }

  _activeTaskId = null;
  _currentReader = null;
  return fullText;
}

function toolDisplayName(name) {
  const map = {
    'mcp__knowledge-mcp__search_knowledge': 'RAG検索',
    'mcp__knowledge-mcp__add_knowledge': 'RAG登録',
    'mcp__knowledge-mcp__list_collections': 'コレクション一覧取得',
    'Read': 'ファイル読込',
    'Grep': 'コード検索',
    'Glob': 'ファイル検索',
    'Bash': 'コマンド実行',
    'Write': 'ファイル書込',
    'Edit': 'ファイル編集',
    'Agent': 'サブエージェント実行',
    'WebSearch': 'Web検索',
    'WebFetch': 'Webページ取得',
  };
  if (map[name]) return map[name];
  if (name.startsWith('mcp__serena__')) return 'コード解析(' + name.replace('mcp__serena__', '') + ')';
  if (name.startsWith('mcp__')) return name.split('__').pop();
  return name;
}

// ── 待機インジケーター ──────────────────────────────
function showWaitingIndicator(container) {
  const isCursorSvc = _isCursorServiceActive('');
  _waitStatusText = isCursorSvc ? 'Cursor で応答を待っています...' : '応答を待っています...';
  const indicator = document.createElement('div');
  indicator.className = 'waiting-indicator';
  indicator.id = 'waitingIndicator';
  indicator.innerHTML = '<div class="spinner"></div><span class="elapsed">' + _waitStatusText + ' 0秒</span>';
  container.appendChild(indicator);
  scrollToBottom();

  _waitStartTime = Date.now();
  _elapsedTimer = setInterval(() => {
    const sec = Math.floor((Date.now() - _waitStartTime) / 1000);
    const elSpan = indicator.querySelector('.elapsed');
    if (elSpan) elSpan.textContent = _waitStatusText + ' ' + sec + '秒';
  }, 1000);

  return indicator;
}

function hideWaitingIndicator() {
  if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
  _waitStartTime = null;
  _waitStatusText = '応答を待っています...';
  const el = document.getElementById('waitingIndicator');
  if (el) el.remove();
}

// ── 送信ボタン ↔ 中止ボタン 切り替え ─────────────────
function setSendMode() {
  const btn = document.getElementById('sendBtn');
  btn.innerHTML = _sendIcon;
  btn.title = '送信';
  btn.onclick = sendMessage;
  btn.classList.remove('cancel-mode');
  btn.disabled = false;
}

function setCancelMode() {
  const btn = document.getElementById('sendBtn');
  btn.innerHTML = _cancelIcon;
  btn.title = '中止';
  btn.onclick = cancelMessage;
  btn.classList.add('cancel-mode');
  btn.disabled = false;
}

async function cancelMessage() {
  if (!_sending) return;
  _cancelled = true;
  const btn = document.getElementById('sendBtn');
  btn.disabled = true;

  // バックエンドにキャンセルリクエスト
  if (_activeTaskId) {
    try {
      await fetch('/api/task/' + _activeTaskId + '/cancel', { method: 'POST' });
    } catch (e) {
      console.warn('キャンセルリクエスト失敗:', e);
    }
  }

  // SSEリーダーを停止
  if (_currentReader) {
    try { _currentReader.cancel(); } catch (_) {}
    _currentReader = null;
  }
}

// ── メッセージ送信 ─────────────────────────────────
async function sendMessage() {
  if (_sending) return;
  if (_viewingHistory) return;  // 読み取り専用中は送信不可

  const input = document.getElementById('messageInput');
  const message = input.value.trim();
  if (!message) { input.focus(); return; }

  _sending = true;
  _messageSaved = false;  // 二重保存防止フラグ
  setCancelMode();
  input.value = '';
  input.style.height = 'auto';
  _manualResized = false;

  // 初回送信時にカテゴリを固定（会話中の変更不可）
  if (!_sessionCreated) {
    _sessionCategory = document.getElementById('categorySelect').value;
  }

  // 添付ファイル情報を取得してクリア
  const attachments = _attachments.slice();
  clearAttachments();

  // ユーザーメッセージ表示（添付がある場合はファイル名も表示）
  let userHtml = '';
  if (attachments.length > 0) {
    userHtml += '<div style="font-size:12px;opacity:0.85;margin-bottom:4px;display:flex;flex-wrap:wrap;gap:4px;align-items:center">';
    attachments.forEach(a => {
      if (a.type === 'image') {
        userHtml += '<img src="' + a.content + '" style="max-height:80px;max-width:120px;object-fit:contain;border-radius:4px;border:1px solid rgba(0,0,0,0.15);" title="' + esc(a.name) + '">';
      } else {
        userHtml += '<span style="background:rgba(0,0,0,0.1);padding:2px 6px;border-radius:3px">[' + esc(a.name) + ']</span>';
      }
    });
    userHtml += '</div>';
  }
  userHtml += '<p>' + esc(message).replace(/\n/g, '<br>') + '</p>';
  appendMessage('user', userHtml, false, { rawText: message });

  // AI 回答プレースホルダー
  const aiDiv = appendMessage('assistant', '', true);
  const aiContent = aiDiv.querySelector('.msg-content');

  const aiSvcEl = document.getElementById('aiServiceSelect');
  _activeRequestAiService = aiSvcEl ? aiSvcEl.value : '';

  // 待機インジケーター表示
  const waitIndicator = showWaitingIndicator(aiContent);

  try {
    const searchAllEl = document.getElementById('searchAllCheck');
    const forkId = _forkFromSessionId;
    _forkFromSessionId = '';  // 1回のみ使用
    const res = await fetch('/api/team-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        mode: document.getElementById('teamSelect').value,
        agents: [],
        history: _conversationHistory,
        model: document.getElementById('modelSelect').value,
        category: document.getElementById('categorySelect').value,
        search_all: searchAllEl ? searchAllEl.checked : false,
        attachments,
        workspace_project: document.getElementById('workspaceProjectSelect').value,
        ai_service: _activeRequestAiService,
        fork_session_id: forkId,
        session_id: _sessionId,
      }),
    });

    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'サーバエラー');
    }

    // 最初のチャンクが届いたら待機表示を消す（processSSEStream 内で処理）
    let firstChunk = true;
    const fullText = await processSSEStream(res, aiContent, aiDiv, null, () => {
      if (firstChunk) {
        firstChunk = false;
        hideWaitingIndicator();
      }
    });

    // 回答完了後: タイトル抽出・除去して保存 + コピー/DLボタン追加
    if (_cancelled) {
      // 中止: 部分回答があれば履歴に保存（UIは processSSEStream 内で設定済み）
      aiDiv.classList.remove('typing');
      if (fullText) {
        const cleanAnswer = stripTitleTag(fullText) + '\n\n[中止されました]';
        _conversationHistory.push({ question: message, answer: cleanAnswer });
        await saveConversation(message, cleanAnswer, '');
        _messageSaved = true;
      }
    } else if (fullText) {
      const title = extractTitle(fullText) || message.slice(0, 40);
      const summary = extractSummary(fullText);
      const cleanAnswer = stripSummaryTag(stripTitleTag(fullText));
      const titleHtml = buildTitleHtml(title, _sessionId, _sequence);
      aiContent.innerHTML = titleHtml + mdToHtml(cleanAnswer);

      // Mermaid / draw.io 図のレンダリング + コードブロックボタン
      await renderMermaidBlocks(aiContent);
      await renderDrawioBlocks(aiContent);
      addCodeBlockButtons(aiContent);

      // 元テキストを data-* 属性に保持
      aiDiv.setAttribute('data-raw-markdown', cleanAnswer);
      aiDiv.setAttribute('data-question', message);
      if (title) aiDiv.setAttribute('data-title', title);

      // コピー/ダウンロードボタンを追加（重複防止）
      if (!aiDiv.querySelector('.msg-actions')) {
        aiDiv.appendChild(createMsgActions());
      }

      // 確認ボタン表示（Allow/Deny、はい/いいえ）
      _showConfirmationButtons(aiDiv, cleanAnswer);

      // 保存してサイドバー更新（awaitで確実に反映）
      _conversationHistory.push({ question: message, answer: cleanAnswer, summary: summary || '' });
      _checkTurnWarning(_conversationHistory.length);
      const convId = await saveConversation(message, cleanAnswer, title, summary);
      if (convId) aiDiv.setAttribute('data-conv-id', convId);
      _messageSaved = true;
    }

  } catch (e) {
    if (_cancelled) {
      // ユーザーによる中止
      hideWaitingIndicator();
      aiDiv.classList.remove('typing');
      const partialText = aiDiv.getAttribute('data-raw-markdown') || '';
      if (!aiContent.innerHTML.includes('[中止されました]')) {
        aiContent.innerHTML = (partialText ? mdToHtml(partialText) : '')
          + '<p style="color:#e67e22;font-size:13px;margin-top:8px;">[中止されました]</p>';
      }
    } else if (_activeTaskId && !_recovering) {
      // SSE接続が切断されたがバックグラウンドタスクは継続中 → ポーリングで復帰
      _recovering = true;
      console.log('SSE切断、ポーリングで復帰を試みます: task=' + _activeTaskId);
      const recovered = await recoverTask(_activeTaskId, aiContent, aiDiv, message);
      _recovering = false;
      if (!recovered) {
        aiDiv.classList.remove('typing');
        aiContent.innerHTML = '<p style="color:#c0392b">接続が切断され、復帰にも失敗しました。</p>';
      }
    } else {
      hideWaitingIndicator();
      aiDiv.classList.remove('typing');
      aiContent.innerHTML = '<p style="color:#c0392b">' + esc(e.message) + '</p>';
    }
  } finally {
    hideWaitingIndicator();
    _activeRequestAiService = '';
    _activeTaskId = null;
    _currentReader = null;
    _sending = false;
    _cancelled = false;
    _recovering = false;
    setSendMode();
    input.focus();
  }
}

// ── バックグラウンドタスク復帰 ─────────────────────
async function recoverTask(taskId, aiContent, aiDiv, question) {
  const pollInterval = 60000;  // 60秒間隔
  const maxAttempts = 1440;    // 60秒間隔 × 1440 = 24時間
  let serverDownSince = null;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch('/api/task/' + taskId);
      if (res.ok) {
        serverDownSince = null;  // サーバー復帰
        const data = await res.json();
        if (data.status === 'done') {
          hideWaitingIndicator();
          const fullText = data.text;
          if (fullText) {
            const title = extractTitle(fullText);
            const summary = extractSummary(fullText);
            const cleanAnswer = stripSummaryTag(stripTitleTag(fullText));
            const titleHtml = buildTitleHtml(title, _sessionId, _sequence);
            aiContent.innerHTML = titleHtml + mdToHtml(cleanAnswer);
            await renderMermaidBlocks(aiContent);
            await renderDrawioBlocks(aiContent);
            addCodeBlockButtons(aiContent);
            aiDiv.setAttribute('data-raw-markdown', cleanAnswer);
            aiDiv.setAttribute('data-question', question);
            if (title) aiDiv.setAttribute('data-title', title);
            aiDiv.classList.remove('typing');
            if (!aiDiv.querySelector('.msg-actions')) {
              aiDiv.appendChild(createMsgActions());
            }
            _showConfirmationButtons(aiDiv, cleanAnswer);
            if (!_messageSaved) {
              _conversationHistory.push({ question, answer: cleanAnswer, summary: summary || '' });
              _checkTurnWarning(_conversationHistory.length);
              const convId2 = await saveConversation(question, cleanAnswer, title, summary);
              if (convId2) aiDiv.setAttribute('data-conv-id', convId2);
              _messageSaved = true;
            }
          }
          return true;
        } else if (data.status === 'error') {
          hideWaitingIndicator();
          aiDiv.classList.remove('typing');
          aiContent.innerHTML = '<p style="color:#c0392b">' + esc(data.error || 'エラーが発生しました') + '</p>';
          return true;
        } else if (data.status === 'cancelled') {
          // キャンセル済み: 部分テキストがあれば表示して終了
          hideWaitingIndicator();
          aiDiv.classList.remove('typing');
          if (data.text) {
            aiContent.innerHTML = mdToHtml(data.text)
              + '<p style="color:#e67e22;font-size:13px;margin-top:8px;">[中止されました]</p>';
            aiDiv.setAttribute('data-raw-markdown', data.text);
            aiDiv.setAttribute('data-question', question);
            if (!_messageSaved) {
              _conversationHistory.push({ question, answer: data.text + '\n\n[中止されました]' });
              await saveConversation(question, data.text + '\n\n[中止されました]', '');
              _messageSaved = true;
            }
          } else {
            aiContent.innerHTML = '<p style="color:#e67e22">[中止されました]</p>';
          }
          return true;
        }
        // running: 部分テキストを表示して続行
        if (data.text) {
          aiContent.innerHTML = mdToHtml(data.text);
          scrollToBottom();
        }
      } else if (res.status === 404) {
        // タスクが見つからない: サーバー再起動でメモリがクリアされた可能性
        // 直前にサーバーダウンを検知していたら「再起動された」と判断
        if (serverDownSince) {
          aiDiv.classList.remove('typing');
          aiContent.innerHTML =
            '<p style="color:#e67e22">サーバーが再起動されました。会話履歴は保存済みです。新しいメッセージで作業を再開してください。</p>';
          return true;
        }
        return false;
      }
    } catch (_) {
      // ネットワークエラー = サーバーダウン中
      if (!serverDownSince) serverDownSince = Date.now();
    }
    await new Promise(r => setTimeout(r, pollInterval));
  }
  return false;
}

function newChat() {
  _sessionId = generateUUID();
  _sequence = 0;
  _sessionCreated = false;
  _sessionCategory = '';
  _conversationHistory = [];
  _viewingHistory = false;
  _viewingSessionId = null;
  _claudeSessionId = '';
  _forkFromSessionId = '';
  _parentSessionId = '';

  // 添付クリア
  clearAttachments();

  // 読み取り専用モードを解除
  document.getElementById('readonlyBanner').classList.remove('visible');
  document.getElementById('inputArea').classList.remove('disabled');

  const chat = document.getElementById('chat');
  chat.innerHTML = '<div class="state" id="emptyState">質問を入力して送信してください。</div>';

  // サイドバーのアクティブ表示をクリア
  updateActiveSession('');

  document.getElementById('messageInput').focus();
  closeSidebar();

  // セッション一覧を再読み込み（アクティブ表示の更新のため）
  loadSessions();
}

// ── 会話分岐 ────────────────────────────────────────

// 予算配分型コンテキスト圧縮
// 直近3ターン: tiered 300/1000/2000字
// それ以前の全ターン: 2000字の予算内で動的圧縮しひとつの要点エントリとして挿入
function _buildTieredHistory(convs) {
  const TIERED_LIMITS = [300, 1000, 2000];
  const OLD_BUDGET = 2000;
  const Q_LIMIT = 50;

  const recent = convs.slice(-3);
  const older  = convs.slice(0, convs.length - 3);

  // 直近3ターン: tiered truncation
  const tieredEntries = recent.map((conv, i) => {
    const maxLen = TIERED_LIMITS[i];
    const summary = conv.summary || '';
    if (summary) {
      return { question: conv.question || '', answer: summary, summary };
    }
    const answer = conv.answer || '';
    return {
      question: conv.question || '',
      answer: answer.length > maxLen ? answer.slice(0, maxLen) + '\n...(省略)' : answer,
    };
  });

  if (older.length === 0) return tieredEntries;

  // 古いターン: 2000字予算を均等分配
  // 各ターン = Q冒頭50字 + A冒頭 perTurnBudget字
  const perTurnBudget = Math.max(30, Math.floor(OLD_BUDGET / older.length) - Q_LIMIT - 15);
  const summaryLines = older.map((conv, i) => {
    const q = (conv.question || '').slice(0, Q_LIMIT).replace(/\n/g, ' ');
    const s = conv.summary || '';
    if (s) {
      const sStr = s.slice(0, perTurnBudget) + (s.length > perTurnBudget ? '…' : '');
      const qStr = q + ((conv.question || '').length > Q_LIMIT ? '…' : '');
      return `[T${i + 1}] Q: ${qStr} / ${sStr}`;
    }
    const a = (conv.answer   || '').slice(0, perTurnBudget).replace(/\n/g, ' ');
    const qStr = q + ((conv.question || '').length > Q_LIMIT ? '…' : '');
    const aStr = a + ((conv.answer   || '').length > perTurnBudget ? '…' : '');
    return `[T${i + 1}] Q: ${qStr} / A: ${aStr}`;
  });

  const compressedEntry = {
    question: `【以前の会話の要点（${older.length}ターン分）】`,
    answer: summaryLines.join('\n'),
  };

  return [compressedEntry, ...tieredEntries];
}

async function forkSession() {
  const sourceId = _viewingHistory ? _viewingSessionId : _sessionId;
  if (!sourceId) {
    showToast('分岐元のセッションが特定できません');
    return;
  }

  // newChat()前に親セッションの会話を取得
  let parentConvs = [];
  try {
    const res = await fetch('/api/sessions/' + encodeURIComponent(sourceId));
    if (res.ok) {
      const data = await res.json();
      parentConvs = data.conversations || [];
    }
  } catch (e) {
    console.warn('親セッション取得失敗（文脈なしで継続）:', e);
  }

  newChat();
  // newChat() が変数をクリアするため、その後にセットする
  _parentSessionId = sourceId;

  // tiered history を注入（取得できた場合のみ）
  if (parentConvs.length > 0) {
    _conversationHistory = _buildTieredHistory(parentConvs);
  }

  const input = document.getElementById('messageInput');
  input.value = `会話履歴ID ${sourceId} の会話の続きです。\n\n`;
  input.focus();
  showToast('分岐モードで新しい会話を開始します。メッセージを追加して送信してください。');
}

// ── 会話保存 ────────────────────────────────────────
async function saveConversation(question, answer, title, summary) {
  try {
    const body = { session_id: _sessionId, sequence: _sequence, question, answer };
    if (!_sessionCreated) {
      // 初回保存時にセッションも作成
      const fallbackTitle = title || question.slice(0, 40);
      const sessPayload = { session_id: _sessionId, title: fallbackTitle, first_message: question, category: _sessionCategory };
      if (_parentSessionId) sessPayload.parent_session_id = _parentSessionId;
      const sessRes = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sessPayload),
      });
      if (!sessRes.ok) {
        console.error('セッション作成失敗:', sessRes.status);
        showToast('会話の保存に失敗しました（セッション作成エラー）');
        return null;
      }
      _sessionCreated = true;
      _parentSessionId = '';  // 1回のみ使用
    }
    if (title) body.title = title;
    if (summary) body.summary = summary;
    const convRes = await fetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!convRes.ok) {
      console.error('会話保存失敗:', convRes.status);
      showToast('会話の保存に失敗しました');
      return null;
    }
    const convData = await convRes.json();
    _sequence++;

    // 保存後にサイドバーのセッション一覧を更新
    loadSessions();
    return convData.id || null;
  } catch (e) {
    console.error('会話保存エラー:', e);
    showToast('会話の保存に失敗しました（通信エラー）');
    return null;
  }
}

// ── Web検索結果の記憶バナー ────────────────────────────
function _showWebSearchMemoryBanner(aiDiv, answerText) {
  const banner = document.createElement('div');
  banner.className = 'web-search-memory-banner';
  banner.innerHTML = `
    <span>Web検索の情報が含まれています。記憶しますか？</span>
    <button class="ws-mem-yes" onclick="_saveWebSearchToStaging(this)">記憶する</button>
    <button class="ws-mem-no" onclick="this.closest('.web-search-memory-banner').remove()">不要</button>
  `;
  banner.dataset.answer = answerText;
  aiDiv.appendChild(banner);
}

async function _saveWebSearchToStaging(btn) {
  const banner = btn.closest('.web-search-memory-banner');
  const answer = banner.dataset.answer || '';
  // 直前のユーザーメッセージを取得
  const chat = document.getElementById('chat');
  const userMsgs = chat.querySelectorAll('.msg.user');
  const lastUser = userMsgs[userMsgs.length - 1];
  const query = lastUser ? lastUser.querySelector('.msg-content')?.textContent?.trim() || '' : '';

  btn.disabled = true;
  btn.textContent = '保存中...';
  try {
    const res = await fetch('/api/save-web-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, content: answer, session_id: _sessionId }),
    });
    if (res.ok) {
      banner.innerHTML = '<span style="color:#27ae60;">記憶しました（バッチ処理後にRAG登録されます）</span>';
      setTimeout(() => banner.remove(), 5000);
    } else {
      banner.innerHTML = '<span style="color:#e74c3c;">保存に失敗しました</span>';
    }
  } catch (e) {
    banner.innerHTML = '<span style="color:#e74c3c;">通信エラー</span>';
  }
}

// ── クイック確認ボタン ──────────────────────────────────
// Claudeが確認を求める返答をしたときに Allow/Deny・はい/いいえ ボタンを表示する

const _CONFIRM_PATTERNS = [
  // Allow/Deny: ファイル書き込み・コマンド実行などの権限承認を求めているとき
  {
    regex: /「Allow」|「Deny」|承認をお願い|承認.*ダイアログ|ダイアログ.*承認|Allow.*クリック|承認.*クリック|許可.*クリック/i,
    buttons: [
      { label: 'Allow', value: 'Allow', style: 'allow' },
      { label: 'Deny',  value: 'Deny',  style: 'deny'  },
    ],
  },
  // はい/いいえ: 続行・対応・実行などの確認を求めているとき
  {
    regex: /進めますか[？?]|続けますか[？?]|対応.*ますか[？?]|修正.*ますか[？?]|実行.*ますか[？?]|移動.*ますか[？?]|削除.*ますか[？?]|作成.*ますか[？?]|設定.*ますか[？?]|よろしいですか[？?]/,
    buttons: [
      { label: 'はい',   value: 'はい',   style: 'allow' },
      { label: 'いいえ', value: 'いいえ', style: 'deny'  },
    ],
  },
];

function _showConfirmationButtons(aiDiv, fullText) {
  if (aiDiv.querySelector('.confirm-banner')) return;

  for (const pattern of _CONFIRM_PATTERNS) {
    if (pattern.regex.test(fullText)) {
      const banner = document.createElement('div');
      banner.className = 'confirm-banner';

      const label = document.createElement('span');
      label.textContent = '確認：';
      banner.appendChild(label);

      pattern.buttons.forEach(btn => {
        const button = document.createElement('button');
        button.className = 'confirm-btn confirm-btn-' + btn.style;
        button.textContent = btn.label;
        button.onclick = () => _sendQuickReply(btn.value, banner);
        banner.appendChild(button);
      });

      aiDiv.appendChild(banner);
      break;
    }
  }
}

function _sendQuickReply(value, banner) {
  if (_sending || _viewingHistory) return;
  if (banner) banner.querySelectorAll('button').forEach(b => { b.disabled = true; });
  const input = document.getElementById('messageInput');
  input.value = value;
  sendMessage();
}
