# 開発ガイドライン

> **前提**: 一般的なコーディング規約・Git 規約・テスト規約は以下に委譲：
> - `everything-claude-code` (ECC) `plankton-code-quality`
> - `andrej-karpathy-skills`
> - `superpowers:test-driven-development` / `verification-before-completion`
> - `prp-commit`
> - `~/.claude/rules/common/` + `~/.claude/rules/{lang}/`
>
> このドキュメントは**プロジェクト固有のルール**のみ。

## プロジェクト固有のコーディングルール

### ドメイン特有の制約

- {例: 金額は常に minor unit（¢ 単位）で Integer 型として扱う}
- {例: 日付は UTC で保存、表示時のみタイムゾーン変換}
- {例: ユーザー ID は `user_` プレフィックス付き ULID}

### 禁止パターン

- {例: 生 SQL 禁止、必ず ORM 経由}
- {例: `any` 型禁止、必要なら `unknown` + 型ガード}
- {例: `process.env` 直接参照禁止、`config.ts` 経由}

### 必須パターン

- {例: 外部 API 呼び出しは `services/` 配下、Zod でレスポンス検証}
- {例: 状態変更を伴う操作はサーバー側で再検証}

## 命名規則（プロジェクト固有分）

ドメイン用語は [`glossary.md`](./glossary.md) 参照。

| カテゴリ | 規則 | 例 |
|---|---|---|
| イベント名 | 動詞 + 名詞、現在形 | `createTask`, `updateUser` |
| エラークラス | `{Domain}Error` サフィックス | `ValidationError`, `AuthError` |
| React フック | 機能を表す動詞句 | `useCurrentUser`, `useDebounce` |
| API エンドポイント | RESTful 複数形 | `GET /api/tasks` |

## スタイリング規約

詳細: `~/.claude/rules/web/coding-style.md`

### Tailwind CSS

- ユーティリティクラス優先、カスタム CSS 最小限
- デザイントークンは `tailwind.config.ts` で統一
- `@apply` は共通パターンのみ（1 回しか使わないものは使わない）

## アクセシビリティ

詳細: [`accessibility.md`](./accessibility.md)

プロジェクト固有の厳しい要件（WCAG 2.2 AAA 等）がある場合のみここに追記。

## セキュリティ（プロジェクト固有）

詳細: [`security.md`](./security.md)

- {例: 会員の PII は `services/pii/` 経由でのみ読み書き、暗号化列を使用}
- {例: 管理画面 API は同一オリジン + セッション Cookie 必須、JWT は使わない}

## ドキュメントコメント

- 関数の意図が非自明な場合のみ JSDoc を付ける
- 自明な処理には書かない（コード自身が語る）
- WHY（なぜ）を書く。WHAT（何を）はコードが示す

## パフォーマンス（プロジェクト固有）

詳細: [`performance.md`](./performance.md)

- {例: リスト表示は 100 件超で仮想スクロール必須}
- {例: 画像は常に `next/image` 経由、CLS 0.1 以下を維持}

## 禁止事項（プロジェクト固有）

- {例: ライブラリ追加は PR で議論（バンドルサイズ管理）}
- {例: `localStorage` に機密情報保存禁止、HttpOnly Cookie 使用}

## 変更時の規律

- このファイルを更新したら該当する既存コードも同時に適合させる
- 規約を追加するときは、その規約が必要になった理由（インシデント等）を追記
