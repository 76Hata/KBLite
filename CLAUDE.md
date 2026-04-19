# KBLite プロジェクト向け Claude Code 設定

## 2層タスク管理ルール（必読）

このプロジェクトでは **Claude Code の `TodoWrite`** と **KBLite の `kblite-tasks` MCP** を
役割分担して併用する。

### 使い分け

| 種別 | 使うツール | scope | 例 |
|---|---|---|---|
| **セッション内の細かい進捗** | `TodoWrite` / `TodoRead` | session | 「今から5ファイル順に直す」「テスト→ビルド→デプロイ」 |
| **大きな案件・複数セッションにまたがる作業** | `mcp__kblite-tasks__task_*` | global | 「2層タスク管理システムの実装」「認証リファクタ」 |
| **ユーザーが追加した項目** | KBブラウザのタスクパネル | global | ユーザー手動入力 |

### 禁止事項

- **セッション内の細粒度タスクを `task_create` で登録しない**。`TodoWrite` を使うこと。
- **大きな案件を `TodoWrite` のみで管理しない**。セッション終了で見失う。`task_create` で scope=global として登録すること。

### 自動連携（実装済み）

- PostToolUse hook が `TodoWrite` の書き込みを検知し、`~/.claude/todos/*.json` を
  `scripts/sync_todowrite.py` 経由で tasks テーブルに後追い同期する（`source=todowrite`, `scope=session`）。
- SessionStart hook が `scripts/session_start_banner.py` を呼び出し、未完了の
  大きな案件（scope=global）を冒頭に提示する。
- `task_resume_context` ツールは scope=global を優先表示し、session を参考情報として分離する。

### task 作成時のデフォルト

- `task_create` は既定で `scope='global'`, `source='manual'`。
- `TodoWrite` 経由のものは自動的に `scope='session'`, `source='todowrite'` で記録されるので
  手動で `scope='session'` を指定する必要は無い。

## セッション再開時の挙動

ユーザーが「前回の続き」等と言及した場合、確認を求めず直ちに `task_resume_context` を呼び、
未完了の大きな案件（scope=global）を最初に提示する。

## データ構造

`tasks` テーブル（`stores/task_mixin.py` / `mcp_tasks.py` で共有）:

| 列 | 型 | 用途 |
|---|---|---|
| `source` | TEXT | `'manual'` / `'todowrite'` / `'mcp'` — タスクの出どころ |
| `scope` | TEXT | `'global'` / `'session'` — 有効範囲 |
| `todo_key` | TEXT | TodoWrite同期用の一意キー（`{session_id}:{todo_id}`） |

- `todo_key` には UNIQUE インデックスが張られており、TodoWrite 側で同一 id の更新があれば
  UPSERT で同一行が更新される。
