/**
 * file-path-linkify.js — AI回答本文に含まれる絶対ファイルパスを検出してクリッカブル化する。
 *
 * 使い方: mdToHtml(...) で生成した要素(例 aiContent / div)を linkifyFilePaths(elem) に渡す。
 * 対応パス形式:
 *   - Windows絶対パス: C:\Users\... / C:/01_Develop/...
 *   - UNIX絶対パス  : /home/... /Users/...
 *   - チルダホーム  : ~/.claude/...
 * <pre>/<a>内のパスはリンク化しない(コードブロック/既リンクを壊さない)。<code>内は対象。
 * クリック時に /api/open_file にPOSTしてOS既定アプリでファイルを開く。
 */
(function () {
  'use strict';

  // 許可終端記号: 日本語句読点・丸括弧・角括弧(リンクを過検出しない)・空白
  // パス先頭は [A-Za-z]: または / または ~/ または ~\
  // 中括弧(}) はパス全体を取り込むため除外リストから外す(後段でプレースホルダー判定)
  var PATH_REGEX =
    /(?:[A-Za-z]:[\\\/][^\s<>"'`、。，．\)\]]+|~[\\\/][^\s<>"'`、。，．\)\]]+|\/(?:Users|home|etc|opt|var|mnt|root)\/[^\s<>"'`、。，．\)\]]+)/g;

  // プレースホルダー({...})・ワイルドカード(*/?)・省略記号(...) を含むパスは
  // 実在しない表記のためリンク化しない
  function isPlaceholderPath(s) {
    return /[{}*?]/.test(s) || /\.{3,}/.test(s);
  }

  var SKIP_TAGS = { PRE: 1, A: 1, SCRIPT: 1, STYLE: 1, TEXTAREA: 1, BUTTON: 1 };

  function showFileToast(msg, isError) {
    var toast = document.createElement('div');
    toast.textContent = msg;
    toast.style.cssText = [
      'position:fixed', 'bottom:24px', 'right:24px', 'z-index:9999',
      'padding:10px 16px', 'border-radius:6px', 'font-size:13px',
      'color:#fff', 'max-width:420px', 'word-break:break-all',
      'box-shadow:0 2px 8px rgba(0,0,0,0.3)',
      isError ? 'background:#c62828' : 'background:#2e7d32'
    ].join(';');
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 3500);
  }

  async function openFileInEditor(path) {
    console.log('[file-path-linkify] クリック:', path);
    try {
      var res = await fetch('/api/open_file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
      });
      if (!res.ok) {
        var err = {};
        try { err = await res.json(); } catch (_) {}
        var msg = err.detail || err.error || ('HTTP ' + res.status);
        console.error('[file-path-linkify] エラー:', msg, 'パス:', path);
        showFileToast('ファイルを開けませんでした: ' + msg, true);
      } else {
        console.log('[file-path-linkify] 成功:', path);
        showFileToast('エディタで開いています: ' + path, false);
      }
    } catch (e) {
      var emsg = e && e.message ? e.message : String(e);
      console.error('[file-path-linkify] fetch失敗:', emsg);
      showFileToast('通信エラー: ' + emsg, true);
    }
  }

  function trimTrailingPunctuation(s) {
    // 末尾のカンマ・ピリオド・セミコロン・コロンは「文末記号」として除外
    return s.replace(/[\.,;:]+$/, '');
  }

  function processTextNode(textNode) {
    var text = textNode.nodeValue;
    if (!text) return;
    PATH_REGEX.lastIndex = 0;
    if (!PATH_REGEX.test(text)) return;
    PATH_REGEX.lastIndex = 0;

    var frag = document.createDocumentFragment();
    var lastIdx = 0;
    var m;
    while ((m = PATH_REGEX.exec(text)) !== null) {
      var rawMatch = m[0];
      var trimmed = trimTrailingPunctuation(rawMatch);
      var matchStart = m.index;
      var matchEnd = matchStart + trimmed.length;

      if (matchStart > lastIdx) {
        frag.appendChild(document.createTextNode(text.slice(lastIdx, matchStart)));
      }

      // プレースホルダー/ワイルドカード混在のパスはリンク化せず原文のまま残す
      if (isPlaceholderPath(trimmed)) {
        frag.appendChild(document.createTextNode(rawMatch));
        lastIdx = matchStart + rawMatch.length;
        continue;
      }

      var span = document.createElement('span');
      span.className = 'file-path-link';
      span.textContent = trimmed;
      span.title = 'クリックで既定のアプリで開く: ' + trimmed;
      span.setAttribute('role', 'button');
      span.setAttribute('tabindex', '0');
      (function (p) {
        span.addEventListener('click', function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          openFileInEditor(p);
        });
        span.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            openFileInEditor(p);
          }
        });
      })(trimmed);
      frag.appendChild(span);

      // 末尾句読点を元に戻す
      if (matchEnd < matchStart + rawMatch.length) {
        frag.appendChild(document.createTextNode(rawMatch.slice(trimmed.length)));
      }
      lastIdx = matchStart + rawMatch.length;
    }
    if (lastIdx < text.length) {
      frag.appendChild(document.createTextNode(text.slice(lastIdx)));
    }
    textNode.parentNode.replaceChild(frag, textNode);
  }

  function linkifyFilePaths(root) {
    if (!root || !root.nodeType) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentNode;
        while (p && p !== root) {
          if (SKIP_TAGS[p.nodeName]) return NodeFilter.FILTER_REJECT;
          p = p.parentNode;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var texts = [];
    var n;
    while ((n = walker.nextNode())) texts.push(n);
    for (var i = 0; i < texts.length; i++) processTextNode(texts[i]);
  }

  // グローバル公開(index.htmlのインラインscriptから typeof ガード付きで呼び出し)
  window.linkifyFilePaths = linkifyFilePaths;
  window.openFileInEditor = openFileInEditor;
})();
