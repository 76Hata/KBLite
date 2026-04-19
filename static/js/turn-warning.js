// turn-warning.js — 会話が10ターンを超えた時点で新規チャット開始を推奨するアラート

const _TURN_WARNING_THRESHOLD = 10;

function _showTurnWarningDialog() {
  // 既に表示中なら二重表示しない
  if (document.getElementById('turnWarningOverlay')) return;

  const overlay = document.createElement('div');
  overlay.id = 'turnWarningOverlay';
  overlay.style.cssText = [
    'position:fixed', 'inset:0', 'background:rgba(0,0,0,0.75)',
    'z-index:10000', 'display:flex', 'align-items:center', 'justify-content:center'
  ].join(';');

  const dlg = document.createElement('div');
  dlg.style.cssText = [
    'background:#1e1e2e', 'border:2px solid #f87171', 'border-radius:12px',
    'padding:28px 36px', 'max-width:420px', 'text-align:center', 'color:#fff',
    'box-shadow:0 8px 32px rgba(0,0,0,0.6)'
  ].join(';');
  dlg.innerHTML =
    '<div style="font-size:2.5em;margin-bottom:12px">&#x1F4AC;</div>' +
    '<h3 style="color:#f87171;margin:0 0 10px;font-size:1.1em">会話が10ターンを超えました</h3>' +
    '<p style="color:#aaa;margin:0 0 20px;font-size:0.88em;line-height:1.6">' +
    '会話が長くなるとプロンプトサイズが増大し、<br>コスト・応答精度に影響します。<br>新規チャットの開始を推奨します。' +
    '</p>' +
    '<button id="turnWarnCloseBtn" style="background:#f87171;border:none;color:#fff;' +
    'padding:8px 28px;border-radius:6px;cursor:pointer;font-size:0.95em">閉じる</button>';
  overlay.appendChild(dlg);
  document.body.appendChild(overlay);
  document.getElementById('turnWarnCloseBtn').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
}

function _checkTurnWarning(turnCount) {
  if (turnCount === _TURN_WARNING_THRESHOLD) {
    _showTurnWarningDialog();
  }
}
