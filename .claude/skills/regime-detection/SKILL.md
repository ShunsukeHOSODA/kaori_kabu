---
name: regime-detection
description: HMM (Hidden Markov Model) で市場レジームを Bull / Choppy / Crisis の 3 状態に自動分類する。hmmlearn を使用、log_returns + realized vol + VIX を投入。信号灯 UI で「現在の市場の機嫌」を可視化、Crisis 時には新規買いを控える規律を提供。Use when ユーザーが「市場環境」「リスクオン/オフ」「相場の状態」「いつ買えばいい？」と発話したとき。
---

# HMM レジーム検出

## 概要

市場の状態を **Bull（上昇）/ Choppy（停滞）/ Crisis（下落）** の 3 段階で自動判定する。HMM は隠れた状態遷移を学習する確率モデルで、リターン・ボラティリティ・VIX 等の特徴量からレジームを推定する。

**目的**:
- Crisis 時に新規買いを控え、現金比率を上げる規律
- 「相場の機嫌」を信号灯で可視化（緑/黄/赤）
- 状態遷移確率も表示（現在からの変化見込み）

## 実装

### 特徴量準備

```python
def prepare_features(prices: pd.DataFrame, vix: pd.Series) -> pd.DataFrame:
    log_returns = np.log(prices / prices.shift(1))
    realized_vol = log_returns.rolling(20).std() * np.sqrt(252)
    return pd.DataFrame({
        "log_return": log_returns,
        "realized_vol": realized_vol,
        "vix": vix,
    }).dropna()
```

### HMM モデル学習

```python
from hmmlearn.hmm import GaussianHMM

model = GaussianHMM(
    n_components=3,
    covariance_type="full",
    n_iter=1000,
    random_state=42,
)
model.fit(features.values)
```

### 状態の解釈（命名）

各 state の平均リターン・ボラから命名:
- Bull = 高リターン + 低ボラ
- Crisis = 低リターン + 高ボラ
- Choppy = その中間

## 信号灯 UI

| 状態 | 色 | 推奨アクション |
|---|---|---|
| Bull | 🟢 | リスクオン、Magic Formula 結果から積極買い OK |
| Choppy | 🟡 | 横ばい、新規買いは慎重に、配当株中心 |
| Crisis | 🔴 | リスクオフ、新規買い停止、現金比率 30%+ |

## 完了時のチェックリスト

- [ ] 3 状態（Bull / Choppy / Crisis）に分類
- [ ] 過去 2 年（504 営業日）から学習
- [ ] 状態遷移確率も表示
- [ ] 信号灯 UI で表示（緑 / 黄 / 赤）
- [ ] 現在の状態に応じた行動推奨を併記
- [ ] HMM の限界（過去依存、状態数の人為性）を併記
