# テスト戦略

> **前提**: TDD は `superpowers:test-driven-development` が強制。検証は `superpowers:verification-before-completion`。このファイルはプロジェクト固有の戦略のみ。

## テストピラミッド

```
       /\
      /  \    E2E (10%)
     /----\   重要 user flow のみ
    /      \  Playwright
   /--------\
  /          \  Integration (20%)
 /            \  API + DB を含む
/______________\
                 Unit (70%)
                 ロジック・ユーティリティ・コンポーネント
                 Vitest + Testing Library
```

| 層 | 比率 | ツール | 速度 | 信頼性 |
|---|---|---|---|---|
| Unit | 70% | Vitest | ms | 高 |
| Integration | 20% | Vitest + testcontainers | sec | 中 |
| E2E | 10% | Playwright | min | 中 |

## カバレッジ目標

| 範囲 | 目標 | 測定 |
|---|---|---|
| 全体 | 80%+ | `vitest --coverage` |
| 変更ファイル（PR） | 90%+ | Codecov diff coverage |
| 重要モジュール（auth, payment, etc.） | 95%+ | フォルダ単位で別計測 |

## TDD ワークフロー（必須）

`superpowers:test-driven-development` に準拠：

1. **RED**: 失敗するテストを書く
2. **GREEN**: 最小限の実装でテストを通す
3. **IMPROVE**: リファクタリング、テストは保持

```bash
pnpm test --watch    # 開発中は watch モード
```

## 各層の書き方

### Unit Test（70%）

- ロジック関数、ユーティリティ、純粋関数中心
- React コンポーネントは Testing Library で「ユーザーが見える挙動」をテスト
- DOM detail（class 名等）に依存しない

```typescript
// 例: utility
import { calculateTax } from './tax';

describe('calculateTax', () => {
  it('returns 0 for amount 0', () => {
    expect(calculateTax(0, 0.1)).toBe(0);
  });
  it('rounds to integer (minor unit)', () => {
    expect(calculateTax(123, 0.1)).toBe(12);
  });
});
```

### Integration Test（20%）

- API ルート + DB（testcontainers で実 DB 起動）
- フロントエンドは Mock Service Worker (MSW) で API を mock
- 状態管理ストア + DB の整合性確認

### E2E Test（10%）

- 重要 user flow のみ（login, payment, primary CTA）
- 環境別実行（local / staging）
- 並列実行で速度確保

```typescript
// 例: Playwright
test('user can create task', async ({ page }) => {
  await page.goto('/login');
  await page.fill('[name=email]', 'user@example.com');
  await page.fill('[name=password]', 'password');
  await page.click('button:has-text("Login")');
  await expect(page).toHaveURL('/dashboard');
  await page.click('button:has-text("New Task")');
  await page.fill('[name=title]', 'My task');
  await page.click('button:has-text("Create")');
  await expect(page.locator('text=My task')).toBeVisible();
});
```

## Visual Regression

UI 重要箇所は Visual Regression：
- ツール: Playwright snapshot / Chromatic / Percy
- 対象: ホーム、主要 CTA、ダッシュボード
- 頻度: PR 毎

## Mock 戦略

| 対象 | Mock 方法 |
|---|---|
| 外部 API | MSW（unit/integration）/ recorded fixture |
| DB | testcontainers（integration）/ in-memory（unit） |
| 時刻 | `vi.useFakeTimers()` |
| ID 生成 | DI で注入可能に |

## CI でのテスト実行

詳細: `.github/workflows/ci.yml`

```
PR 開く → unit/integration（並列）→ build → E2E → security audit
```

## テストの臭い（避けるべき）

- ❌ 実装詳細をテスト（class 名、内部 state）
- ❌ 巨大なフィクスチャの hardcode
- ❌ flaky test を放置（quarantine ディレクトリへ移動して修正）
- ❌ 偶然 pass するテスト（assertion なし、空 try-catch）

## Flaky Test 対応

1. 検出: 連続 fail rate > 1% で flaky 認定
2. 隔離: `tests/quarantine/` に移動 + GitHub Issue
3. 期限: 1 sprint 以内に修正
4. 期限超過: 削除 + ADR で記録
