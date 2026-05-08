---
name: polymarket-macro-watcher
description: Polymarket Gamma API（無料・認証不要）から Fed 利上げ・米選挙・景気後退・地政学イベントの市場織り込み確率を取得する。マクロ判断の客観的シグナルとして活用。Use when ユーザーが「Fed 利上げ確率」「景気後退の可能性」「マクロイベント」「Polymarket」と発話したとき。
---

# Polymarket マクロウォッチャー

## 概要

Polymarket は予測市場の代表格。実際の資金で取引されているため、市場参加者の総合的な期待値（実勢確率）を反映する。Gamma API は無料・認証不要・60 req/min で利用可能。

**用途**:
- Fed 利上げ・利下げ確率
- 米大統領選・議会選挙
- 景気後退（recession）
- 地政学リスク
- インフレ率予測

## API エンドポイント

```python
BASE_URL = "https://gamma-api.polymarket.com"

# 全マーケット取得
markets = httpx.get(f"{BASE_URL}/markets", params={
    "active": "true",
    "closed": "false",
    "limit": 100,
}).json()
```

## レート制限対応

```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=60, period=60)  # 60 req/min
def polymarket_api_call(endpoint: str, params: dict = None):
    return httpx.get(f"{BASE_URL}{endpoint}", params=params).json()
```

## キャッシュ戦略

1 時間キャッシュ（マクロは秒単位で動かない）。

## 投資判断への活用

| シグナル | アクション |
|---|---|
| Fed 利下げ確率 70%+ | 長期国債 / グロース株のオーバーウェイト検討 |
| 景気後退確率 50%+ | 現金比率 30%+ に上げる、シクリカル株削減 |
| 選挙でセクター変動予測 | 影響セクター（ヘルスケア、エネルギー等）の調整 |

## 完了時のチェックリスト

- [ ] レート制限 60 req/min 厳守
- [ ] 1 時間キャッシュ実装
- [ ] outcome の正規化（合計 100% に）
- [ ] 流動性（24h volume）併記
- [ ] Polymarket の限界（規制、流動性）を併記
- [ ] マクロシグナルから具体的アクション提案
