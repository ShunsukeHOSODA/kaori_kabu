## Summary

<!-- 何を / なぜ / どう を 1-3 行で -->

## Type of Change

- [ ] feat: 新機能
- [ ] fix: バグ修正
- [ ] refactor: リファクタリング（外部挙動変わらず）
- [ ] perf: パフォーマンス改善
- [ ] docs: ドキュメント
- [ ] test: テスト追加
- [ ] chore: その他（ビルド、CI 等）

## 関連 Issue / Doc

<!-- Closes #123 / docs/ADR/0007-xxx.md / .steering/20260507-xxx/ -->

## 変更内容

- 

## テスト

- [ ] Unit tests 追加・更新
- [ ] Integration tests 追加・更新
- [ ] E2E tests 追加・更新（重要 user flow）

### Test plan

```
1. このブランチをチェックアウト
2. pnpm install
3. pnpm dev
4. http://localhost:3000/xxx で〇〇を確認
```

## スクリーンショット / 動画

| Before | After |
|---|---|
| (画像) | (画像) |

## 影響範囲

- [ ] 既存機能への影響なし
- [ ] DB マイグレーションあり → backward-compatible: yes / no
- [ ] 環境変数追加・変更あり → `.env.example` 更新済み
- [ ] 外部 API への依存追加あり
- [ ] 破壊的変更あり（API/UI/DB）→ migration guide 記載済み

## Pre-merge チェックリスト

- [ ] CI がパスしている
- [ ] `code-reviewer` agent でレビュー済み
- [ ] `security-reviewer` agent でレビュー済み（auth/payment/PII 系の場合）
- [ ] `superpowers:verification-before-completion` を実施
- [ ] 関連 docs/ を更新（基本設計に影響あれば）
- [ ] CHANGELOG に追記（該当する場合）
- [ ] feature flag で gating（リスクある変更の場合）

## レビュー依頼

- 確認してほしい論点: 
- 特に見てほしいファイル: 

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
