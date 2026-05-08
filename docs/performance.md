# パフォーマンス目標と測定

> **前提**: Web パフォーマンス全般は `~/.claude/rules/web/performance.md` 参照。このファイルはプロジェクト固有の目標と測定方法。

## Core Web Vitals 目標

| 指標 | Good | 改善必要 | 目標 |
|---|---|---|---|
| **LCP**（Largest Contentful Paint） | < 2.5s | 2.5-4.0s | < 2.5s |
| **INP**（Interaction to Next Paint） | < 200ms | 200-500ms | < 200ms |
| **CLS**（Cumulative Layout Shift） | < 0.1 | 0.1-0.25 | < 0.1 |
| **FCP**（First Contentful Paint） | < 1.8s | 1.8-3.0s | < 1.5s |
| **TTFB**（Time to First Byte） | < 800ms | 0.8-1.8s | < 600ms |

測定: PageSpeed Insights / Lighthouse / Chrome UX Report (CrUX)

## API パフォーマンス目標

| メトリクス | 目標 |
|---|---|
| p50 レイテンシ | < 100ms |
| p95 レイテンシ | < 500ms |
| p99 レイテンシ | < 1000ms |
| エラー率 | < 0.1% |
| スループット | {例: 1000 req/sec} |

## バンドル予算

| 項目 | 目標 |
|---|---|
| Initial JS（gzipped） | < 150 KB |
| Initial CSS | < 30 KB |
| Total JS（PR 1 ページ） | < 300 KB |
| 画像（hero） | < 200 KB |

CI で監視: `bundlesize` / `size-limit`

## 最適化チェックリスト

### 初期表示

- [ ] Hero 画像 preload（`<link rel="preload">`）
- [ ] Critical CSS inline（above-the-fold）
- [ ] 非クリティカル CSS は defer
- [ ] フォント `font-display: swap`
- [ ] 重い JS は dynamic import

### レンダリング

- [ ] Compositor-friendly プロパティのみ animate（transform / opacity）
- [ ] `will-change` を narrow に使う
- [ ] スクロールハンドラは IntersectionObserver で代替
- [ ] React: memo / useMemo / useCallback は計測してから

### ネットワーク

- [ ] HTTP/2 or HTTP/3
- [ ] CDN 利用
- [ ] cache-control header 設定
- [ ] 画像は AVIF / WebP（fallback あり）
- [ ] 画像に `width` / `height` 明示（CLS 防止）

### サードパーティ

- [ ] async / defer
- [ ] 自分のドメインから serve（self-host 検討）
- [ ] SRI（Subresource Integrity）
- [ ] 不要なら削除

## 測定方法

### Real User Monitoring (RUM)

- ツール: Vercel Analytics / Sentry Performance / Datadog RUM
- 全ユーザーのデータ収集
- 95 パーセンタイル中心に評価

### ラボ環境

- Lighthouse CI（CI で実行）
- WebPageTest（複雑なシナリオ）
- 4G ネットワーク + ミドルレンジ端末でシミュレート

### ベンチマーク（API）

- k6 / Artillery / wrk
- ステージング環境で本番相当負荷

## 性能リグレッション検出

- Lighthouse CI を PR で実行
- 主要メトリクスが目標を超えたら PR ブロック
- 例外時は ADR で記録 + 後で修正計画

## このプロジェクトの追加要件

- {例: モバイル 3G 環境で初期表示 < 5 秒}
- {例: ダッシュボード 100 件表示時のスクロール 60 fps 維持}
