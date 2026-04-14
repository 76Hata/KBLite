/**
 * KBLite Browser UI - Client-side rendering
 * Markdown / Code Highlight / Mermaid / DOMPurify
 */
document.addEventListener("DOMContentLoaded", function () {
    // marked.js の設定
    if (typeof marked !== "undefined") {
        marked.setOptions({
            breaks: true,
            gfm: true,
        });
    }

    // mermaid の初期化
    if (typeof mermaid !== "undefined") {
        mermaid.initialize({ startOnLoad: false, theme: "default" });
    }

    // .markdown-content 要素を処理
    var elements = document.querySelectorAll(".markdown-content");
    var mermaidIndex = 0;

    elements.forEach(function (el) {
        var raw = el.textContent;
        if (!raw || !raw.trim()) return;

        // marked でパース
        var html = typeof marked !== "undefined" ? marked.parse(raw) : raw;

        // DOMPurify でサニタイズ
        if (typeof DOMPurify !== "undefined") {
            html = DOMPurify.sanitize(html, {
                ALLOWED_TAGS: [
                    "h1", "h2", "h3", "h4", "h5", "h6", "p", "a", "ul", "ol", "li",
                    "code", "pre", "blockquote", "table", "thead", "tbody", "tr",
                    "th", "td", "strong", "em", "br", "hr", "img", "mark", "span",
                    "div", "input"
                ],
                ALLOWED_ATTR: ["href", "src", "alt", "class", "id", "type", "checked", "disabled"]
            });
        }

        el.innerHTML = html;

        // highlight.js でコードブロックをハイライト
        if (typeof hljs !== "undefined") {
            el.querySelectorAll("pre code").forEach(function (block) {
                hljs.highlightElement(block);
            });
        }

        // mermaid ブロックの変換
        if (typeof mermaid !== "undefined") {
            el.querySelectorAll("code.language-mermaid").forEach(function (code) {
                var pre = code.parentElement;
                var container = document.createElement("div");
                container.className = "mermaid";
                container.textContent = code.textContent;
                var id = "mermaid-" + mermaidIndex++;
                container.setAttribute("id", id);
                pre.replaceWith(container);
            });
        }
    });

    // mermaid の描画実行
    if (typeof mermaid !== "undefined") {
        var mermaidEls = document.querySelectorAll(".mermaid");
        if (mermaidEls.length > 0) {
            mermaid.run({ nodes: mermaidEls });
        }
    }
});
