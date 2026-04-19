/**
 * file-path-linkify.js — AI回答本文に含まれる絶対ファイルパスを検出してクリッカブル化する。
 *
 * 使い方: mdToHtml(...) で生成した要素(例 aiContent / div)を linkifyFilePaths(elem) に渡す。
 * 対応パス形式:
 *   - Windows絶対パス: C:\Users\... / C:/01_Develop/...
 *   - UNIX絶対パス  : /home/... /Users/...
 *   - チルダホーム  : ~/.claude/...
 * <code>/<pre>/<a>内のパスはリンク化しない(コード/既リンクを壊さない)。
 * クリック時に /api/open_file にPOSTしてOS既定アプリでファイルを開く。
 */
(function () {
  'use strict';

  // 許可終端記号: 日本語句読点・丸括弧(リンクを過検出しない)・空白
  // パス先頭は [A-Za-z]: または / または ~/ または ~\
  var PATH_REGEX =
    /(?:[A-Za-z]:[\\\/][^\s<>"'`、。，．\)\]\}]+|~[\\\/][^\s<>"'`、。，．\)\]\}]+|\/(?:Users|home|etc|opt|var|mnt|root)\/[^\s<>"'`、。，．\)\]\}]+)/g;

  var SKIP_TAGS = { CODE: 1, PRE: 1, A: 1, SCRIPT: 1, STYLE: 1, TEXTAREA: 1, BUTTON: 1 };

  async function openFileInEditor(path) {
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
        alert('ファイルを開けませんでした\n\nパス: ' + path + '\n理由: ' + msg);
      }
    } catch (e) {
      alert('ファイルを開けませんでした\n\n' + (e && e.message ? e.message : e));
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
