# Observability — ログ・メトリクス・トレース

> **目的**: 障害時に「何が」「いつ」「なぜ」起きたかを 5 分以内に特定可能にする。

## 三本柱

| 柱 | 何 | ツール例 |
|---|---|---|
| **Logs** | イベントの記録（誰が何をしたか） | Logtail / Axiom / Datadog Logs |
| **Metrics** | 数値の集約（負荷、エラー率、レイテンシ） | Prometheus / Datadog / Grafana |
| **Traces** | リクエストの経路（どのサービスでどれだけ時間） | Jaeger / Tempo / Datadog APM |

## ログ

### 形式

**構造化ログ（JSON）必須**。`console.log` 禁止。

```typescript
import { logger } from '@/lib/logger';

logger.info('task.created', {
  task_id: task.id,
  user_id: user.id,
  request_id: ctx.requestId,
  latency_ms: 42,
});
```

### 必須フィールド

| フィールド | 説明 |
|---|---|
| `timestamp` | ISO 8601、UTC |
| `level` | debug / info / warn / error |
| `event` | snake_case のイベント名 |
| `request_id` | リクエスト相関 ID（W3C trace-context） |
| `user_id` | 認証済みなら（PII 除外） |
| `service` | service name |

### ログレベル指針

- `debug`: 開発中のみ。production では出さない
- `info`: 正常な業務イベント（ログイン成功、注文完了）
- `warn`: 異常だが処理継続（リトライ発動、deprecated API 利用）
- `error`: エラー（処理失敗、unhandled exception）

### 機密情報の取り扱い

- パスワード / token / 個人情報は **ログに出さない**
- マスキング必須: `email: "u***@example.com"`、`card: "**** **** **** 1234"`
- ロガーレベルでフィルタ（pii redactor 推奨）

## メトリクス

### RED メソッド（API / サービス）

- **Rate**: 秒間リクエスト数
- **Errors**: エラー率（%）
- **Duration**: レイテンシ p50, p95, p99

### USE メソッド（リソース）

- **Utilization**: CPU / Memory / Disk 使用率
- **Saturation**: キュー長、connection pool 待機
- **Errors**: ハードウェア / OS エラー

### ビジネスメトリクス

| メトリクス | 例 |
|---|---|
| 主要アクション数 | タスク作成数 / 時 |
| 転換率 | 訪問 → サインアップ |
| エラー率 | 決済失敗率 |

### 目標値（SLO）

| メトリクス | 目標 | 測定窓 |
|---|---|---|
| 可用性 | 99.9% | 30 日 |
| API p95 レイテンシ | < 500ms | 7 日 |
| エラー率 | < 0.1% | 7 日 |

詳細: `~/.claude/rules/web/performance.md`

## トレース（OpenTelemetry）

- 標準: **OpenTelemetry**（ベンダーロックイン回避）
- export: OTLP → Datadog / Tempo / Jaeger 等

```typescript
import { trace } from '@opentelemetry/api';

const tracer = trace.getTracer('app');

async function createTask(input: CreateTaskInput) {
  return tracer.startActiveSpan('createTask', async (span) => {
    span.setAttribute('user.id', input.userId);
    try {
      const task = await db.tasks.create(input);
      return task;
    } catch (err) {
      span.recordException(err);
      throw err;
    } finally {
      span.end();
    }
  });
}
```

## 相関 ID

リクエスト相関 ID を全層で伝播：

- 入口（middleware）で `request_id` を生成 or 引き継ぎ（`X-Request-Id` header）
- ログ・メトリクス・トレース全部に付与
- 外部 API 呼び出し時にも `X-Request-Id` を渡す（可能なら）

## エラーモニタリング

- ツール: **Sentry**（推奨）
- 自動キャプチャ: unhandled exception / Promise rejection
- 手動: `Sentry.captureException(err, { tags: {...} })`
- DSN は環境変数 `SENTRY_DSN`

## アラート

| 重大度 | 条件 | 通知先 |
|---|---|---|
| 🔴 P0 | 主要機能停止 | PagerDuty + Slack #incidents |
| 🟠 P1 | エラー率 > 1% (5 分連続) | Slack #incidents |
| 🟡 P2 | レイテンシ p95 > 1s (10 分連続) | Slack #engineering |
| 🟢 P3 | バックログ蓄積、将来予兆 | 日次 digest |

詳細: [`runbooks/incident-response.md`](./runbooks/incident-response.md)

## ダッシュボード

最低限用意：

- **Service Health**: RED + 主要ビジネスメトリクス
- **Errors**: 直近 24h の error トップ
- **Performance**: Core Web Vitals 推移
- **Cost**: LLM API / hosting コスト

## ヘルスチェック

```typescript
// /api/health
{
  "status": "ok" | "degraded" | "down",
  "version": "1.2.3",
  "uptime_sec": 12345,
  "checks": {
    "db": "ok",
    "cache": "ok",
    "external_api": "degraded"
  }
}
```

## ローカル開発時

`docker-compose.yml` で OTel collector + Grafana を立ち上げて開発時もトレース確認可能にする。
