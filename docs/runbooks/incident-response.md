# Runbook: インシデント対応

> **目的**: 本番障害発生時に 5 分以内に行動を開始する

## 重大度（severity）

| 重大度 | 定義 | 例 |
|---|---|---|
| 🔴 SEV-1 | 主要機能停止、データ消失リスク | サイト全体ダウン、決済不可 |
| 🟠 SEV-2 | 主要機能の大部分が動かない | ログイン不可、API エラー > 50% |
| 🟡 SEV-3 | 限定的影響 | 一部機能のエラー、性能劣化 |
| 🟢 SEV-4 | 軽微 | typo、UI ずれ |

## 初動 5 分

```
① 通知受信
   ↓ 1 分
② 状況確認（Sentry / Datadog ダッシュボード）
   ↓ 2 分
③ severity 判定（上の表）
   ↓ 1 分
④ 関係者通知（severity に応じて）
   ↓ 1 分
⑤ 初期対応（rollback / mitigation）
```

## 関係者通知

| Severity | 通知先 | 通知方法 |
|---|---|---|
| SEV-1 | All hands | PagerDuty + Slack #incidents + status page |
| SEV-2 | Engineering | Slack #incidents |
| SEV-3 | チームリード | Slack #engineering |
| SEV-4 | 通常 PR 経由 | - |

## 状況確認チェックリスト

- [ ] Sentry: 直近のエラー（rate, message, affected users）
- [ ] Datadog / Vercel Analytics: latency, error rate, throughput
- [ ] DB: connection pool, slow queries, replication lag
- [ ] 外部 API status page（Stripe, OpenAI, etc.）
- [ ] CDN: cache hit rate, edge errors
- [ ] 直近 deploy（24h 以内？）→ rollback 検討

## 軽減策（Mitigation）

優先順位：

### Tier 1: 即時可能

- **Rollback**（直前 deploy が原因）→ [`rollback.md`](./rollback.md)
- **feature flag off**（特定機能の問題）
- **Rate limit 強化**（過負荷時）

### Tier 2: 数分

- **CDN cache hit rate を上げる**（origin 過負荷）
- **DB query 制限**（特定 endpoint を 503 で返す）
- **circuit breaker 発動**

### Tier 3: 緊急修正

- **hotfix PR**（root cause 明確な場合）
- **dependency rollback**（external API breaking change 時）

## コミュニケーション

### Slack #incidents の使い方

```
🔴 [SEV-1] サイト全体ダウン
時刻: 2026-MM-DD HH:MM JST
状況: production がレスポンス返さない
影響: 全ユーザー
担当: @hosodashunsuke
ステータス: 調査中

(更新は thread に追記)
```

### Status Page

SEV-1 / SEV-2 では status page を更新（顧客向け）。

### 事後（24 時間以内）

- ポストモーテム作成（テンプレート: `templates/postmortem.md`）
- ADR を必要に応じて作成
- 該当 runbook を更新

## ポストモーテム項目

1. **タイムライン**: 発生 → 検知 → 通知 → 軽減 → 解決
2. **影響**: 影響ユーザー数、影響時間、損失（売上 / SLO 消費）
3. **根本原因**: なぜ起きたか（5 whys）
4. **再発防止**: アクション + 担当 + 期限
5. **学び**: 何が良かったか（blameless）

## 連絡先

- オンコール: PagerDuty 設定参照
- DBA: @{担当}
- セキュリティ: @{担当}
- 法務（PII 漏洩時）: @{担当}
