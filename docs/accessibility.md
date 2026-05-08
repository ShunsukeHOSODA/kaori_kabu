# アクセシビリティ

> **目標**: WCAG 2.2 AA 準拠。`a11y-architect` agent を必要に応じて起動。

## なぜ a11y か

- 法的要件（地域による：ADA, EU Accessibility Act, JIS X 8341）
- 利用可能ユーザー拡大（高齢者、視覚・運動障害、一時的な制約 = 片手使用、明るい屋外）
- SEO ・モバイル対応との整合（セマンティック HTML が両方に効く）

## 基準

**WCAG 2.2 AA** 準拠を必須とする。

主要原則（POUR）:

| 原則 | 意味 |
|---|---|
| **P**erceivable | 知覚可能（テキスト代替、キャプション、コントラスト） |
| **O**perable | 操作可能（キーボード、十分な時間、発作トリガー回避） |
| **U**nderstandable | 理解可能（読みやすい、予測可能、入力支援） |
| **R**obust | 堅牢（assistive tech との互換性） |

## 必須チェック

### キーボード操作

- [ ] **すべての操作がキーボードのみで完了**
- [ ] フォーカスインジケータが視認可能（2px 以上、3:1 コントラスト）
- [ ] フォーカストラップが意図的（modal）/ 意図せず（バグ）の区別
- [ ] Tab order が論理的
- [ ] Skip link（"Skip to main content"）

### スクリーンリーダー

- [ ] セマンティック HTML（`<button>`, `<nav>`, `<main>`, `<h1>`〜`<h6>`）
- [ ] 必要なら ARIA（過剰使用禁止、ネイティブ要素優先）
- [ ] aria-label / aria-labelledby が意味的に正しい
- [ ] live region（`aria-live`）でエラー・トースト通知
- [ ] 画像に意味があれば alt、装飾なら `alt=""`

### コントラスト

- 通常テキスト: 4.5:1 以上
- 大きいテキスト（18pt+ または 14pt+ bold）: 3:1
- UI コンポーネント / グラフィカル要素: 3:1
- 測定: Lighthouse / axe DevTools / Stark

### フォーム

- [ ] `<label>` を全 input に紐付け
- [ ] エラーメッセージが input と関連付け（`aria-describedby`）
- [ ] required は `aria-required="true"`
- [ ] 適切な input type（`email`, `tel`, `number`）
- [ ] autocomplete 属性

### 動き

- [ ] `prefers-reduced-motion` を尊重
- [ ] 自動再生は user gesture 後 or オフ可能
- [ ] フラッシュは 1 秒間に 3 回未満（発作トリガー回避）

### 画像・メディア

- [ ] 全画像に意味的な alt
- [ ] 動画にキャプション
- [ ] 動画に音声解説（必要なら）

## 自動チェック

CI でのチェック：

- **axe-core**（Playwright プラグイン）
- **eslint-plugin-jsx-a11y**
- **Lighthouse CI**（accessibility category）

```typescript
// 例: Playwright + axe
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('home page has no a11y violations', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

## 手動テスト

自動では検出できない：

- スクリーンリーダー実機テスト（VoiceOver / NVDA）
- キーボードのみで全機能完走
- 200% ズームでレイアウト崩れなし
- Color blind シミュレータ（Chrome DevTools）

## このプロジェクトの追加要件

- {例: WCAG 2.2 AAA を主要画面のみ満たす}
- {例: 日本語 UI のため、漢字読み上げ確認を加える}
