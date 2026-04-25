"""プロンプト構築 — エージェント命令文・カテゴリ指示・会話履歴の組み立て"""

from deps import AGENT_COMMANDS_DIR, CATEGORIES, store

# ── 定型インストラクション ────────────────────────────────────────

_IMAGE_INSTRUCTION = ""

_DIAGRAM_INSTRUCTION = """
# 図表生成ルール
回答の理解を助けるために、以下のような場合はMermaidコードブロックで図を生成してください:
- システム構成図・アーキテクチャ図
- 処理フロー・手順の説明
- データの関係性（ER図）
- 状態遷移・ライフサイクル
- 比較・分類の整理（マインドマップ）
- タイムライン・スケジュール（ガントチャート）

Mermaid記法のルール:
- ノード名・ラベル・サブグラフ名に絵文字・特殊記号・全角罫線文字を使用しない
- 日本語テキスト・英数字・基本記号のみ使用する
- マルチバイト文字（日本語等）を含むラベルは必ずダブルクォート（"）で囲む（囲まないと描画されない）
  - 正: A["質問する"] --> B["RAG検索"]
  - 誤: A[質問する] --> B[RAG検索]
- 図が不要な場合や単純な回答には無理に図を入れない
"""

_DRAWIO_INSTRUCTION = """
# draw.io図表生成ルール
以下のような複雑な図が必要な場合は、draw.io XML形式（```drawio コードブロック）で出力できます:
- 複雑なネットワーク構成図・インフラ構成図
- 自由配置が必要なアーキテクチャ図
- 位置や色を細かく制御したい図
- Mermaidでは表現しきれない複雑なレイアウト

draw.io XMLの基本構造:
```drawio
<mxfile>
  <diagram name="図名">
    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- ノード: value=表示テキスト, style=スタイル -->
        <mxCell id="2" value="ノード名" style="rounded=1;whiteSpace=wrap;" vertex="1" parent="1">
          <mxGeometry x="100" y="100" width="120" height="60" as="geometry"/>
        </mxCell>
        <!-- エッジ: source/target でノードを接続 -->
        <mxCell id="3" value="" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="2" target="4" parent="1"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

ルール:
- 簡単な図やフロー図はMermaid記法を優先すること
- draw.ioはMermaidでは表現困難な複雑図にのみ使用すること
- mxCell の id は重複させないこと
- value属性に日本語テキストを使用可能
"""

_TITLE_INSTRUCTION = """
# タイトル生成ルール（必須）
回答の最後に、この質問と回答の内容を要約した短いタイトル（20文字以内の日本語）を
以下のHTMLコメント形式で必ず出力してください。このタイトルは会話履歴の一覧表示に使用されます。
<!-- KB_TITLE: タイトルテキスト -->
"""

_TURN_SUMMARY_INSTRUCTION = """
# ターン要約の出力（必須）
回答の最後（KB_TITLEの後）に、このターンの内容を構造化した要約を以下のHTMLコメント形式で
必ず出力してください。この要約は次ターン以降の会話履歴として使用されます。

要約は「引き継ぎ文書」として機能します。次のターンのAIがこの要約だけを読んで
会話を円滑に継続できることを最優先にしてください。
文字数は各フィールド目安であり、必要に応じて超過しても構いません。

<!-- KB_TURN_SUMMARY
topic: [このターンの主テーマ（目安30文字）]
background: [前ターンからの文脈・経緯。初回や文脈不要時は省略可]
decisions: [確定した設計・方針・ユーザーの明示的指示（目安200文字）]
changes: [変更したファイル・DB・設定。変更がない場合は省略可]
pending: [次に持ち越す未解決事項・残タスク。なければ省略可]
-->

出力順序: 回答本文 → KB_TITLE → KB_TURN_SUMMARY
"""


_TASK_MANAGEMENT_INSTRUCTION = """
# タスク管理ルール（kblite-tasks MCP）

kblite-tasks MCPサーバーが提供するタスク管理ツールを、以下のルールに従ってプロアクティブに活用してください。

タスクリストはAI自身の作業漏れを防ぐためのワーキングメモリです。ユーザーへの確認は不要で、積極的に登録・消化・削除してください。

## タスク登録の判断基準

以下に該当する依頼は、**ユーザーに確認せず直ちに `task_create` を呼んで自動登録する**こと。「このタスクをタスクリストに登録しますか？」のような確認は行わない。

- 複数のファイル変更・複数ステップを伴う実装依頼（「〜を作って」「〜を追加して」等）
- フェーズ計画・設計議論など、複数ターンにわたることが明白な作業
- 「後でやる」「今度やる」「メモしておいて」と明示された事項
- 複雑なバグ修正・調査（原因不明で時間がかかりそうな問題）

**単純な質問・1行の説明・ファイル読み取りのみで完結する依頼は登録しない。**

## タスクライフサイクル管理

| 状況 | 行うべき操作 |
|------|------------|
| 実装に着手する直前 | `task_update` で status → `in_progress` |
| 作業の節目・判断ポイント | `task_add_note` でメモを残す（「○○まで完了」「△△で保留」等） |
| 実装が完了したとき | `task_update` で status → `done` |
| 中断・ブロックされたとき | `task_add_note` に「中断理由」を記録し、status → `blocked` 等に更新 |

## セッション再開時の自動確認

会話履歴に「前回の続き」「前回どこまでやったか」「あの作業どうなった？」等のキーワードがある場合、**ユーザーに確認を求めることなく** `task_resume_context` を呼び、未完了タスクの一覧を最初に提示すること。

## 注意事項

- タスク登録はユーザー確認不要。プロアクティブに実施する
- `task_id` はタスク作成後に取得した値を変数として保持し、後続の `task_update` / `task_add_note` に使う
- タスクタイトルは簡潔に（30文字以内）。詳細は `description` に書く
"""


# ── プロンプト構築関数 ────────────────────────────────────────────


def _build_fast_prompt(message: str) -> str:
    """速度重視モード用のシンプルなインラインプロンプト"""
    return (
        "あなたは優秀なナレッジアシスタントです。\n"
        "ユーザの質問に対して、簡潔かつ正確に回答してください。\n"
        "技術的な質問にはコード例を含めてください。\n\n"
        f"ユーザの質問: {message}"
    )


def load_command_prompt(command_name: str) -> str:
    """~/.claude/commands/{command_name}.md を読み込む"""
    path = AGENT_COMMANDS_DIR / f"{command_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"コマンドファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def _build_history_context(history: list) -> str:
    """会話履歴をプロンプト用テキストに変換する。

    summaryがあるターンは要約を使用し、ないターンは回答全文（最大2000文字）を使用する。
    """
    if not history:
        return ""
    parts = []
    for i, h in enumerate(history):
        q = h.get("question", "")
        summary = h.get("summary", "")
        if summary:
            parts.append(f"### ターン{i + 1}\n質問: {q}\n\n要約:\n{summary}")
        else:
            a = h.get("answer", "")
            if len(a) > 2000:
                a = a[:2000] + "\n...(省略)"
            parts.append(f"### ターン{i + 1}\n質問: {q}\n\n回答:\n{a}")
    return "## 同一セッション内の前回のやり取り\n" + "\n\n".join(parts) + "\n\n"


def _build_category_instruction(category: str, search_all: bool = False) -> str:
    """カテゴリ情報をプロンプトに追加する。RAGはFTS5で自動投入されるため手動検索指示は不要。"""
    if not category or category == "common_knowledge":
        return ""
    cat_name = next((c["name"] for c in CATEGORIES if c["system_id"] == category), category)
    return f"\n\nこの会話のカテゴリは「{cat_name}」(system_id: {category}) です。回答時はこのカテゴリの文脈を考慮してください。\n"


def _build_rag_context(query: str, current_session_id: str = "") -> str:
    """FTS5でクエリに関連する過去の会話を検索し、RAGコンテキストとして整形する"""
    try:
        results = store.fts_search_for_rag(query, limit=3, current_session_id=current_session_id or None)
    except Exception:
        return ""
    if not results:
        return ""
    parts = ["\n\n## 関連する過去の会話（参考情報）"]
    parts.append("以下は過去の会話から検索された関連情報です。回答の参考にしてください。")
    for i, r in enumerate(results, 1):
        session_title = r.get("session_title", "")
        q = r.get("question", "")
        a = r.get("answer", "")
        header = f"### 参考{i}"
        if session_title:
            header += f"（{session_title}）"
        parts.append(header)
        if q:
            parts.append(f"**質問:** {q}")
        if a:
            parts.append(f"**回答:** {a}")
    return "\n".join(parts) + "\n"


def _build_client_context(client_context: str) -> str:
    """クライアント情報をプロンプト用テキストに変換する。"""
    if not client_context:
        return ""
    return (
        "\n\n<client-context>\n"
        f"起動元: {client_context}\n"
        "あなたはKBブラウザ（Webチャット）から起動されています。\n"
        "KBブラウザはCLIと同等のファイル操作・コード変更・Git操作が可能です。\n"
        "ファイル修正・コード変更はツールを使って直接実行してください。ユーザーに手作業を求めないこと。\n"
        "</client-context>\n"
    )


def build_team_prompt(
    message: str,
    agents: list,
    mode: str,
    history: list | None = None,
    category: str = "",
    search_all: bool = False,
    client_context: str = "",
    lesson_context: str = "",
    session_id: str = "",
) -> str:
    """ユーザーメッセージとエージェント選択からプロンプトを構築"""
    history_ctx = _build_history_context(history) if history else ""
    effective_message = f"{history_ctx}## 今回の質問\n{message}" if history_ctx else message
    category_instruction = _build_category_instruction(category, search_all=search_all)
    client_ctx = _build_client_context(client_context)
    rag_ctx = _build_rag_context(message, current_session_id=session_id)

    if mode == "team-it":
        template = load_command_prompt("agent-team-it")
        prompt = template.replace("$ARGUMENTS", effective_message)
    elif mode == "content":
        template = load_command_prompt("agent-team-content")
        prompt = template.replace("$ARGUMENTS", effective_message)
    elif mode == "general":
        template = load_command_prompt("agent-team-general")
        prompt = template.replace("$ARGUMENTS", effective_message)
    elif mode == "childcare":
        template = load_command_prompt("agent-team-childcare")
        prompt = template.replace("$ARGUMENTS", effective_message)
    elif mode == "tax":
        template = load_command_prompt("agent-team-tax")
        prompt = template.replace("$ARGUMENTS", effective_message)
    elif mode == "fast":
        prompt = _build_fast_prompt(effective_message)
        return (
            prompt
            + rag_ctx
            + category_instruction
            + _TITLE_INSTRUCTION
            + _TASK_MANAGEMENT_INSTRUCTION
            + client_ctx
        )
    else:
        parts = []
        for agent_id in agents:
            template = load_command_prompt(agent_id)
            parts.append(template.replace("$ARGUMENTS", effective_message))
        prompt = "\n\n---\n\n".join(parts)
    return (
        prompt
        + _IMAGE_INSTRUCTION
        + _DIAGRAM_INSTRUCTION
        + _DRAWIO_INSTRUCTION
        + rag_ctx
        + category_instruction
        + _TITLE_INSTRUCTION
        + _TURN_SUMMARY_INSTRUCTION
        + _TASK_MANAGEMENT_INSTRUCTION
        + client_ctx
        + lesson_context
    )
