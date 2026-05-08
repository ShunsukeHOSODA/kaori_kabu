---
name: monte-carlo-projection
description: ポートフォリオの将来分布を 1000 パスのモンテカルロシミュレーション（GBM）で表示する。一本線の価格予測を禁止し、5/25/50/75/95 パーセンタイル fan chart で確率分布として表示。numpy + Plotly 実装。Use when ユーザーが「将来の予測」「期待値」「シナリオ分析」と発話したとき、または保有ポートフォリオの将来推移を可視化するとき。
---

# Monte Carlo 確率分布シミュレーション

## 概要

ポートフォリオの将来パスを **幾何ブラウン運動（GBM）** で 1000 本生成し、確率分布として表示する。素人ほど「点予測」（例: 110 万円）でなく「分布」（例: 90% 確率で 80〜140 万円）で考える習慣をつけることが重要。

## 計算式

GBM（幾何ブラウン運動）:

```
S(t+1) = S(t) × exp((μ - σ²/2) × Δt + σ × √Δt × Z)

ここで:
  μ = 過去ヒストリカルからの平均リターン
  σ = 過去ヒストリカルからのボラティリティ
  Δt = 1/252 (日次)
  Z ~ N(0, 1)
```

## 実装

```python
import numpy as np

def gbm_simulation(
    initial_value: float,
    mu: float,
    sigma: float,
    horizon_days: int = 252,
    n_simulations: int = 1000,
    seed: int = 42,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    Z = rng.standard_normal((n_simulations, horizon_days))
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * Z
    log_returns = drift + diffusion
    paths = np.zeros((n_simulations, horizon_days + 1))
    paths[:, 0] = initial_value
    paths[:, 1:] = initial_value * np.exp(np.cumsum(log_returns, axis=1))
    return paths
```

## パーセンタイル計算

```python
percentiles = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
```

## バリエーション

### Bootstrap（リサンプリング、外れ値強い）

過去リターンからランダムサンプリング（正規分布仮定なし）。

### 多銘柄相関考慮（共分散行列使用）

共分散行列の Cholesky 分解で銘柄間相関を保つ。

## 完了時のチェックリスト

- [ ] 最低 1000 シミュレーション
- [ ] 5/25/50/75/95 パーセンタイル明示
- [ ] 一本線予測になっていない
- [ ] GBM の限界（fat tail、相関変動）を併記
- [ ] horizon 切替（1/3/6/12 ヶ月）対応
- [ ] Plotly fan chart で表示
