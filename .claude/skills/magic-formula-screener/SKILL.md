---
name: magic-formula-screener
description: Joel Greenblatt の Magic Formula（ROC + Earnings Yield）で米国・日本市場をスクリーニングする。EBIT/EV と EBIT/(Net WC + Net Fixed Assets) を計算し、両ランキング合計で上位 N 銘柄を抽出。金融・公益・エネルギーを除外、時価総額フィルタを適用。素人向け教育レイヤー付き。Use when ユーザーが「割安銘柄探して」「Magic Formula のスコア計算」「Greenblatt の手法で銘柄選定」と発話したとき。
---

# Magic Formula スクリーナー

## 概要

Joel Greenblatt が "The Little Book That Still Beats the Market" で提唱した Magic Formula を実装する。**ROC（Return on Capital）** と **Earnings Yield** の両方が高い銘柄を抽出することで、「良い会社を安く買う」という Buffett 哲学を数式に落とした手法。

**実証結果（学術的バックボーン）**:
- 米国市場 2000-2022 年: 年率 17.2%（市場平均 8.0%）
- 日本市場（Montier 2006 検証）: +10.8% アウトパフォーム
- 出典: Greenblatt 2010 / Quant Investing 2022 / Montier 2006

## 計算式

```
ROC = EBIT / (Net Working Capital + Net Fixed Assets)
Earnings Yield = EBIT / Enterprise Value
                = EBIT / (Market Cap + Total Debt - Cash)

Magic Formula Score = rank(ROC) + rank(Earnings Yield)
```

## 実装手順

### 1. 銘柄ユニバース取得

- `financedatabase` で米国 NYSE/NASDAQ + 東証一部・グロース全銘柄
- 除外: Financials / Utilities / Energy セクター（ROC 計算が異質）
- フィルタ: 時価総額 ≥ $100M（流動性確保）

### 2. ファンダメンタル取得

- OpenBB SDK 経由で EBIT、Net Working Capital、Net Fixed Assets、Market Cap、Total Debt、Cash
- 直近四半期データ + TTM（Trailing Twelve Months）

### 3. ランキング合算

```python
df['roc_rank'] = df['roc'].rank(ascending=False)
df['ey_rank'] = df['earnings_yield'].rank(ascending=False)
df['mf_score'] = df['roc_rank'] + df['ey_rank']
top_30 = df.nsmallest(30, 'mf_score')
```

### 4. リバランス

- 四半期ごとにリバランス（年 4 回）
- 12 ヶ月以上保有後の銘柄は税務考慮で売却タイミングを調整

## 教育レイヤー（UI 3 段階展開）

```
┌─ Magic Formula スコア: 87/100 ─────────────┐
│  📊 ROC: 28% (上位 5%)                      │
│  💰 Earnings Yield: 12% (上位 15%)          │
│                                             │
│  🤔 なぜ買い候補?  [▼展開]                   │
│   ├─ ROC が高い = 資本効率の良い会社         │
│   ├─ EY が高い = 利益の割に株価が安い        │
│   └─ Greenblatt 2010 のバックテスト: 年率17% │
│                                             │
│  ⚠️ リスク [▼展開]                           │
│   ├─ Value Trap (構造不況業種かもしれない)   │
│   └─ 直近 3 年は MFD アンダーパフォーム      │
│                                             │
│  📚 もっと学ぶ → "The Little Book..."       │
└─────────────────────────────────────────────┘
```

## 完了時のチェックリスト

- [ ] 米国 + 日本 両市場をカバー
- [ ] 金融・公益・エネルギー除外を確認
- [ ] 時価総額 $100M フィルタ適用
- [ ] 各銘柄に学術的根拠を併記
- [ ] Value Trap 警告を表示
- [ ] CSV エクスポート可能
