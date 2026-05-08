---
name: kelly-position-sizer
description: Kelly Criterion でポジションサイズを数学的に最適化し、Half-Kelly（× 0.5）で破滅リスクを回避する。1 銘柄上限 5%、現金準備 10% を強制。バックテストから勝率と損益比を抽出して自動計算。Use when ユーザーが「ポジションサイズ」「いくら買うべき」「投資配分」と発話したとき。
---

# Half-Kelly ポジションサイザー

## 概要

Kelly Criterion は数学的に最適なベットサイズを与える公式。ただし**フル Kelly は推定誤差で破滅する**ため、実務では **Half-Kelly（× 0.5）** が標準。William Poundstone "Fortune's Formula" で詳述。

## 計算式

```
f* = (bp - q) / b

ここで:
  f* = 資金に対する最適ベット比率
  b = 損益比（平均利益 / 平均損失）
  p = 勝率
  q = 敗率 (1 - p)
```

## 実装

```python
def kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.5,
    max_position: float = 0.05,
) -> float:
    """Half-Kelly ポジションサイズを計算する。"""
    if avg_loss <= 0:
        return 0.0
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p
    full_kelly = (b * p - q) / b
    half_kelly = full_kelly * fraction
    return max(0.0, min(half_kelly, max_position))
```

## なぜ Half-Kelly？

| シナリオ | フル Kelly | Half-Kelly |
|---|---|---|
| 推定誤差なし（理論値） | 最大成長率 | 75% の成長率 |
| 推定誤差あり（現実） | 破滅可能性高 | 安全マージン |
| ドローダウン | 50% も普通 | 25% 程度 |
| 心理的耐久性 | 不可能 | 耐えられる |

**経験則**: Kelly の半分でも理論最適成長率の 75% を達成できる。リスク削減の費用対効果が極めて高い。

## ポートフォリオ全体での適用

```python
def portfolio_position_sizing(
    candidates: list[dict],
    cash_reserve: float = 0.10,
    max_position: float = 0.05,
    fraction: float = 0.5,
) -> pd.DataFrame:
    """複数銘柄の Half-Kelly 配分。合計が 1 - cash_reserve を超える場合は比例縮小。"""
```

## 完了時のチェックリスト

- [ ] フル Kelly 値も併記（参考値、警告付き）
- [ ] Half-Kelly（× 0.5）デフォルト
- [ ] 1 銘柄上限 5% 強制
- [ ] 現金準備 10% 強制
- [ ] バックテストデータが 3 年以上か確認
- [ ] 「フル Kelly でなく Half-Kelly を使う理由」を表示
