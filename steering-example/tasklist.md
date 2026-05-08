# タスク: {タイトル}

## サマリー

- **担当**: 
- **期日**: YYYY-MM-DD
- **優先度**: P0 / P1 / P2

## タスク

### Phase 1: 基盤

- [ ] DB マイグレーション作成（tags table）
- [ ] Drizzle schema 更新
- [ ] migration 適用 (dev / staging)

### Phase 2: API

- [ ] `GET /api/tasks?tags=` 実装
- [ ] `POST /api/tasks/:id/tags` 実装
- [ ] `DELETE /api/tasks/:id/tags/:tagId` 実装
- [ ] zod スキーマ定義
- [ ] ユニットテスト
- [ ] Integration テスト

### Phase 3: UI

- [ ] `TagBadge` コンポーネント
- [ ] `TagInput` コンポーネント
- [ ] タスク詳細画面に統合
- [ ] タスク一覧画面に `TagFilter` 統合
- [ ] storybook（任意）

### Phase 4: テスト・リリース

- [ ] E2E テスト追加
- [ ] feature flag 設定
- [ ] PR 作成（`@claude` レビュー）
- [ ] code-reviewer + security-reviewer
- [ ] staging で確認
- [ ] 本番リリース（feature flag off）
- [ ] beta 開始（10%）
- [ ] GA

### Phase 5: ドキュメント

- [ ] `docs/glossary.md` に Tag 用語追加
- [ ] `docs/functional-design.md` の ER 図更新
- [ ] CHANGELOG 更新
- [ ] vault に学びを記録

## ブロッカー / 質問

- [ ] (なし) / {ブロッカー内容}

## 完了報告

- 完了日: 
- 関連 PR: 
- 関連 ADR: 
- 学び: 
