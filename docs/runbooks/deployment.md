# Runbook: 本番デプロイ手順

## 前提

- main ブランチに必要な変更が merge 済み
- CI が pass している
- 関連 ADR / docs が更新されている

## デプロイ前チェック

- [ ] `git log origin/main..HEAD` が空（local 未 push がない）
- [ ] CI green（GitHub Actions）
- [ ] `npm audit` で HIGH/CRITICAL なし
- [ ] migration がある場合 backward-compatible 確認
- [ ] feature flag が必要なら有効化準備

## 手順

### Vercel の場合（自動デプロイ）

```bash
git push origin main  # → Vercel が自動 deploy
```

確認:
1. https://vercel.com/{org}/{project} で deployment 監視
2. Build log でエラーなし
3. 完了後、production URL で smoke test

### 手動デプロイ（GitHub Actions）

```bash
gh workflow run deploy.yml -f env=production
```

### マイグレーションを伴うデプロイ

1. **backward-compatible マイグレーションを先行 deploy**:
   ```bash
   pnpm db:migrate:dry  # 確認
   pnpm db:migrate      # 実行
   ```
2. アプリコード deploy
3. **不要な古いカラムは別 PR で後日削除**

## デプロイ後の確認（5 分間）

- [ ] `/health` が 200 OK
- [ ] 主要エンドポイント smoke test
- [ ] Sentry でエラー上昇なし
- [ ] Datadog / Vercel Analytics で latency 急増なし
- [ ] Lighthouse CI で性能劣化なし

## 異常時

→ [`rollback.md`](./rollback.md) 実行

## 連絡先

| 状況 | 連絡先 |
|---|---|
| Build 失敗 | Slack #engineering |
| 本番障害 | PagerDuty + Slack #incidents |
| DB 問題 | DBA / @{担当} |

## 関連

- [`/deploy` slash command](../../.claude/commands/deploy.md)
- [`incident-response.md`](./incident-response.md)
