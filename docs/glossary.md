# ユビキタス言語定義

このプロジェクトで使用する用語の定義。実装・ドキュメント・UI・会話で **同じ概念には同じ言葉を使う**。

## ドメイン用語

| 日本語 | 英語（コード上） | 定義 | 使用場面 |
|---|---|---|---|
| {タスク} | Task | ユーザーが実行すべき作業単位 | API・DB・UI |
| {プロジェクト} | Project | 複数のタスクをまとめる単位 | API・DB・UI |
| {担当者} | Assignee | タスクに割り当てられたユーザー | API・UI |
| {期日} | Due Date | タスクの完了期限 | API・UI |

## ビジネス用語

| 日本語 | 英語 | 定義 |
|---|---|---|
| {稼働率} | Utilization Rate | 有効時間に対する実作業時間の割合 |
| {バックログ} | Backlog | 未着手タスクの一覧 |

## UI/UX 用語

| 用語 | 定義 |
|---|---|
| {ダッシュボード} | ユーザーが最初に見る情報集約画面 |
| {サイドパネル} | 画面右側に表示される補助情報エリア |
| {トースト} | 画面下部に数秒表示される一時通知 |

## 技術用語（プロジェクト固有の使い方）

| 用語 | 定義 | 備考 |
|---|---|---|
| {セッション} | サーバー側のログイン状態を保持する期間 | JWT ではなく Cookie ベース |
| {アーカイブ} | 論理削除された状態 | `deleted_at` に日時を記録 |

## 命名規則

### データベース

- テーブル名: `snake_case` 複数形（`tasks`, `user_settings`）
- カラム名: `snake_case`（`created_at`, `user_id`）
- 外部キー: `{参照先単数形}_id`（`user_id`, `project_id`）
- インデックス: `idx_{table}_{columns}`
- 制約: `chk_{table}_{rule}` / `fk_{table}_{column}`

### API

- エンドポイント: `kebab-case` 複数形（`/api/tasks`, `/api/user-settings`）
- JSON フィールド: `snake_case`（DB と一致）または `camelCase`（統一する）
- HTTP メソッド: REST 慣例（GET/POST/PUT/PATCH/DELETE）

### TypeScript

- 型・インターフェース: `PascalCase`（`Task`, `CreateTaskInput`）
- 列挙型: `PascalCase`（`TaskStatus.Pending`）
- 定数: `UPPER_SNAKE_CASE`（`MAX_RETRY_COUNT`）

### イベント / Action

- 動詞 + 名詞、現在形: `createTask`, `updateUser`
- past tense はイベント名: `taskCreated`, `userUpdated`

## 日本語・英語対応表

| 日本語 UI | 英語コード | 備考 |
|---|---|---|
| 作成する | create | `createTask` |
| 編集する | update / edit | 既存を変更 |
| 削除する | delete | 論理削除なら `archive` |
| 完了する | complete | ステータス変更 |
| 開始する | start | |
| 一時停止する | pause | |
| 取り消す | cancel | 処理中の停止 |
| 元に戻す | undo | 直前の操作 |

## 禁止される用語

- ❌ 「リスト」と「一覧」を混在させない → 「一覧」で統一
- ❌ `delete` と `remove` を混在させない → `delete` で統一
- ❌ 「ユーザー」と「利用者」を混在させない → 「ユーザー」で統一

## 用語追加のルール

- 新しいドメイン概念が発生したら即追加
- コードで既に使われている用語は必ず記載
- 英訳に迷ったらチームで合意を取る
- 変更する場合は既存コードの更新計画を `.steering/` で作成してから実施
