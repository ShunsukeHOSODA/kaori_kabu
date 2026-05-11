# Phase 5.2 実装メモ（Task 5.2.0 — 3 Agent 並列調査結果統合）

| 項目 | 値 |
|---|---|
| 作成日 | 2026-05-12 |
| 上位仕様 | `docs/ranking-judge-prd.md` |
| 実装計画 | `.steering/20260512-claude-ranking-judge/design.md` |
| 目的 | Task 5.2.1-5.2.9 で参照する確定事項を集約 |

---

## 1. 確定事項（採用、design.md からの修正点）

### 1.1 モデル ID の訂正 ⚠️ 重要

design.md の仮値 `DEFAULT_MODEL_VERSION = "claude-sonnet-4-6-20260101"` は **誤り**。

確定値: **`claude-sonnet-4-6-20250514`**

根拠: Anthropic 公式 SDK ナレッジ（カットオフ 2025-08 時点）。実機で `anthropic.models.list()` を叩いて差分があれば後で修正可能（settings.py の env var override で吸収予定）。

### 1.2 Pydantic v2 禁止フィールド reject の設計 — 案 C 採用

`extra='forbid'` + `model_validator(mode='before')` の **2 層防御** を採用。3 層防御（system prompt / Pydantic / 正規表現）の単一真実源として `FORBIDDEN_PREDICTION_FIELDS: frozenset[str]` を定数化。

```python
FORBIDDEN_PREDICTION_FIELDS: frozenset[str] = frozenset({
    "target_price", "expected_return", "time_horizon",
    "price_target", "forecast_price",
})


class RankingResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ... フィールド定義 ...

    @model_validator(mode="before")
    @classmethod
    def _reject_prediction_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        hit = FORBIDDEN_PREDICTION_FIELDS & data.keys()
        if hit:
            raise ValueError(
                f"一本線予測フィールド検出 (CLAUDE.md §9.3 違反): {sorted(hit)}"
            )
        return data
```

**注意点**:
- `model_construct` は validator をバイパスするのでテスト / キャッシュ復元で使わない規約
- `model_config` は `ConfigDict` 使用必須（dict literal は禁止）

### 1.3 Prompt Caching シンタックス

```python
client.messages.create(
    model="claude-sonnet-4-6-20250514",
    max_tokens=2048,
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[{"role": "user", "content": user_msg}],
)
```

- **TTL**: 5 分（ephemeral のみ）
- **最小 token**: 2,048（Sonnet 4 系）— **SYSTEM_PROMPT は 2,048 token 以上にする必要あり**
- **最大 cache_control 箇所**: 4

### 1.4 usage / Prompt Caching ヒット判定

```python
input_tokens   = response.usage.input_tokens
output_tokens  = response.usage.output_tokens
cache_read     = response.usage.cache_read_input_tokens or 0       # ヒット時 token
cache_creation = response.usage.cache_creation_input_tokens or 0   # 生成時 token
is_cache_hit   = cache_read > 0
```

- 課金: 初回（生成）は通常の 1.25 倍、2 回目以降（ヒット）は 0.1 倍
- `input_tokens` はキャッシュを除いた非キャッシュ部分のみ

### 1.5 structured output（response_format）

Claude API では **`response_format` パラメータ非対応**。

採用: **system prompt で「JSON のみ返せ」と指示 + `_extract_json()` 後処理**（sentiment.py の既存パターン継承）。

---

## 2. 既存実装の継承戦略

### 2.1 `_extract_json` / `_get_current_git_commit` の扱い

architect は「共通モジュール化推奨」だが、**Phase 5.2 ではスコープ管理のため ranking_judge.py に新規コピー実装** を採用。

理由:
- Phase 5.2 の単一責務（ranking_judge.py 実装）を超えない
- sentiment.py 既存テストへの副作用なし
- 既存パターン（sentiment.py）と冗長になるが、`src/analysis/_common.py` 化は Phase 6 候補

**Phase 6 候補（持ち越し）**: `src/analysis/_common.py` 新規 → sentiment.py + ranking_judge.py の両方から import するように refactor。drift リスクを単一真実源で抑制。

### 2.2 sentiment.py の現状制約（ranking_judge では改善する）

| 項目 | sentiment.py 現状 | ranking_judge.py での扱い |
|---|---|---|
| Prompt Caching | 未使用（`system=` 直渡し） | **使用**（cache_control ephemeral） |
| usage 保存 | metadata に未保存 | **input/output/cached tokens を全部 RankingMetadata に保存** |
| system プロンプト | str | **list[dict] + cache_control** |

---

## 3. テスト戦略

### 3.1 禁止フィールド reject テスト

```python
@pytest.mark.parametrize("forbidden", [
    "target_price", "expected_return", "time_horizon",
    "price_target", "forecast_price",
])
def test_禁止フィールドを個別に reject(forbidden, valid_payload):
    bad = {**valid_payload, forbidden: 200}
    with pytest.raises(ValidationError, match="一本線予測フィールド検出"):
        RankingResult.model_validate(bad)


def test_未知 typo フィールドは forbid 経路で reject(valid_payload):
    bad = {**valid_payload, "rankng_scor": 80}  # typo
    with pytest.raises(ValidationError, match="Extra inputs"):
        RankingResult.model_validate(bad)


def test_FORBIDDEN_PREDICTION_FIELDS_と_PRD_§7_2_の同期():
    assert FORBIDDEN_PREDICTION_FIELDS == frozenset({
        "target_price", "expected_return", "time_horizon",
        "price_target", "forecast_price"})
```

ポイント: parametrize で 5 フィールド個別検証 + typo は別経路 + PRD 定数同期検証。

### 3.2 Prompt Caching ヒット率検証（Phase 5.5）

開発時の Sonnet 呼び出しコスト計算で `is_cache_hit` を集計し、想定の 90% 削減が成立するか実機で確認（Phase 5.5 E2E 時）。

---

## 4. Phase 6 持ち越し候補（Phase 5 完了後）

- `src/analysis/_common.py` 化（`_extract_json` / `_get_current_git_commit` 共通化）
- Sonnet 価格 / モデル ID の動的取得（`anthropic.models.list()` 経由、settings.py override）
- Prompt Caching ヒット率実測ダッシュボード（コスト監視）
- structured output が将来 Claude API でサポートされた場合の移行

---

**notes-5.2.md 終わり** — Task 5.2.1 以降の implementer subagent はこのファイルを必読。
