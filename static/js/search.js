// search.js — FTS5 全文検索UI

let _ftsDebounceTimer = null;

(function initFtsSearch() {
  const input = document.getElementById('ftsSearchInput');
  const clearBtn = document.getElementById('ftsSearchClear');
  if (!input) return;

  input.addEventListener('input', () => {
    clearBtn.style.display = input.value ? 'block' : 'none';
    clearTimeout(_ftsDebounceTimer);
    const q = input.value.trim();
    if (!q) {
      hideFtsResults();
      return;
    }
    _ftsDebounceTimer = setTimeout(() => runFtsSearch(q), 300);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') clearFtsSearch();
  });
})();

async function runFtsSearch(query) {
  const resultsEl = document.getElementById('ftsSearchResults');
  const sessionList = document.getElementById('sessionList');
  if (!resultsEl) return;

  resultsEl.style.display = 'block';
  sessionList.style.display = 'none';
  resultsEl.innerHTML = '<div class="search-no-result">検索中...</div>';

  try {
    const res = await fetch('/api/search?q=' + encodeURIComponent(query) + '&limit=20');
    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      resultsEl.innerHTML = '<div class="search-no-result">該当なし</div>';
      return;
    }

    resultsEl.innerHTML = data.results.map(r => {
      const q = esc(r.question || '').substring(0, 100);
      const a = esc(r.answer || '').substring(0, 150);
      const sid = esc(r.session_id);
      const date = r.created_at ? r.created_at.substring(0, 10) : '';
      const score = r.score ? r.score.toFixed(2) : '';
      return `<div class="search-result-item" onclick="onFtsResultClick('${sid}')">
        <div class="search-result-question">${q}</div>
        <div class="search-result-answer">${a}</div>
        <div class="search-result-meta">${esc(date)}${score ? ' | score: ' + score : ''}</div>
      </div>`;
    }).join('');
  } catch (e) {
    resultsEl.innerHTML = '<div class="search-no-result">検索エラー</div>';
  }
}

function onFtsResultClick(sessionId) {
  clearFtsSearch();
  if (typeof selectSession === 'function') {
    selectSession(sessionId);
  }
}

function clearFtsSearch() {
  const input = document.getElementById('ftsSearchInput');
  const clearBtn = document.getElementById('ftsSearchClear');
  if (input) input.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  hideFtsResults();
}

function hideFtsResults() {
  const resultsEl = document.getElementById('ftsSearchResults');
  const sessionList = document.getElementById('sessionList');
  if (resultsEl) {
    resultsEl.style.display = 'none';
    resultsEl.innerHTML = '';
  }
  if (sessionList) sessionList.style.display = '';
}
