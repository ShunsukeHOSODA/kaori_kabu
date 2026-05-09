# 設計書 — UI 5 タブ再設計

> **要件**: `requirements.md`
> **前提コミット**: `21d2213`
> **基本方針**: 既存ロジックは 1 行も削らず、ナビ露出のみ削減 + ホーム強化

---

## 1. アーキテクチャ概観

### 1.1 ナビゲーション層

```
src/dashboard/app.py
  └─ st.navigation(pages=[8 entries])  ← 5 entries に圧縮
```

非表示にする 4 ページのファイルは **残す**:
- `pages/03_thirteen_f.py`（裏で達人バッジに転用）
- `pages/04_backtest.py`（Step 4 で内部 import）
- `pages/05_monte_carlo.py`（Step 4 で内部 import）
- `pages/06_macro.py`（裏で HMM 信号灯に転用）

### 1.2 既存資産マップ（grounded で確認済み）

| 既存資産 | 場所 | 用途 |
|---|---|---|
| HMM レジーム検出 | `src/analysis/regime.py:306-344` `detect_regime_with_provenance` | Step 2 信号灯 |
| ATR トレーリングストップ | `src/strategies/atr_stop.py:54-81` `calculate_trailing_stop` | Step 2 アラート |
| EODHD クライアント | `src/data/eodhd.py` `get_eod` | VIX & 保有銘柄 OHLC 取得 |
| Composite Score | `src/analysis/composite/aggregator.py` `compute_composite_score` | Step 3 銘柄ランキング |
| Composite プリセット | `src/analysis/composite/presets.py` 4 種（Buffett/配当/Lynch/逆張り） | Step 3 4 カテゴリの素 |
| 投資家レンズ | `src/analysis/investor_lenses.py` 8 投資家 | Step 3 では未使用、将来拡張 |

### 1.3 新規追加コード

| ファイル | 役割 | 規模 |
|---|---|---|
| `src/dashboard/pages/08_research.py` | 銘柄リサーチ（過去/将来タブ統合） | 新規 ~120 行 |
| `src/dashboard/widgets/regime_signal.py` | 信号灯ウィジェット（テスト容易な分離） | 新規 ~60 行 |
| `src/dashboard/widgets/atr_alert.py` | ATR アラート行レンダラ | 新規 ~80 行 |
| `src/data/famous_holdings.py` | 達人保有銘柄の静的辞書（Phase 3.2 で動的化） | 新規 ~30 行 |
| `src/dashboard/widgets/__init__.py` | パッケージ初期化 | 新規空 |
| `src/dashboard/research/__init__.py` | パッケージ初期化 | 新規空 |
| `src/dashboard/research/backtest_panel.py` | 04_backtest のロジック関数化 | 新規 ~80 行 |
| `src/dashboard/research/monte_carlo_panel.py` | 05_monte_carlo のロジック関数化 | 新規 ~80 行 |

### 1.4 編集する既存ファイル

| ファイル | 編集内容 | 規模 |
|---|---|---|
| `src/dashboard/app.py` | `pages` リスト 8→5 に圧縮、welcome テーブル更新 | -約 60 行 |
| `src/dashboard/pages/01_home.py` | 信号灯・ATR アラートセクション追記 | +約 100 行 |
| `src/dashboard/pages/02_screener.py` | 4 カテゴリ + バッジに刷新（既存 Composite 呼び出しは流用） | 大幅改修 |
| `tests/unit/dashboard/widgets/test_regime_signal.py` | 信号灯ロジックの単体テスト | 新規 |
| `tests/unit/dashboard/widgets/test_atr_alert.py` | アラート判定の単体テスト | 新規 |
| `tests/unit/data/test_famous_holdings.py` | 静的辞書の整合性テスト | 新規 |

---

## 2. Step 1: ナビゲーション整理（5 分）

### 2.1 `src/dashboard/app.py:150-187` 編集

**Before**: 8 ページ
**After**: 5 ページ + welcome (default)

```python
pages = [
    st.Page(_welcome_page, title="📈 ようこそ", default=True),
    st.Page(str(_PAGES_DIR / "01_home.py"),     title="🏠 ホーム",         url_path="home"),
    st.Page(str(_PAGES_DIR / "02_screener.py"), title="🔍 おすすめ銘柄",   url_path="screener"),
    st.Page(str(_PAGES_DIR / "08_research.py"), title="🧪 銘柄を調べる",   url_path="research"),
    st.Page(str(_PAGES_DIR / "07_settings.py"), title="⚙️ 設定",           url_path="settings"),
]
```

### 2.2 `_welcome_page()` の使い方テーブル更新（73-86 行）

5 行構成に変更。13F / マクロ / 過去検証 / 将来予測 行を削除し、新項目を反映。

### 2.3 検証
- `streamlit run src/dashboard/app.py` でサイドバーが 5 項目になることを目視
- `pytest -m "not slow" -q` で 223 件 GREEN

---

## 3. Step 2: ホーム強化（60 分）

### 3.1 信号灯ウィジェット — `src/dashboard/widgets/regime_signal.py`

```python
from dataclasses import dataclass
from typing import Literal

import streamlit as st

from src.analysis.regime import RegimeResult


@dataclass(frozen=True)
class RegimeSignal:
    """信号灯表示用の正規化結果。"""
    emoji: Literal["🟢", "🟡", "🔴"]
    label_ja: str               # "強気相場" / "横ばい" / "暴落リスク"
    action_ja: str              # "積極買い OK" / "慎重・配当株中心" / "新規買い停止"
    color: Literal["normal", "warning", "error"]


_LABEL_MAP = {
    "Bull":   RegimeSignal("🟢", "強気相場",   "積極買い OK",       "normal"),
    "Choppy": RegimeSignal("🟡", "横ばい",     "慎重・配当株中心",  "warning"),
    "Crisis": RegimeSignal("🔴", "暴落リスク", "新規買い停止",      "error"),
}


def to_signal(result: RegimeResult) -> RegimeSignal:
    return _LABEL_MAP[result.current_regime]


def render_regime_signal(result: RegimeResult | None, *, container=st) -> None:
    """ホーム画面 1 行で信号灯を表示、折りたたみで詳細。"""
    if result is None:
        container.info("🟢 市場の機嫌: **判定中**（VIX データ取得待ち）")
        return
    signal = to_signal(result)
    msg = f"{signal.emoji} 市場の機嫌: **{signal.label_ja}** — {signal.action_ja}"
    if signal.color == "error":
        container.error(msg)
    elif signal.color == "warning":
        container.warning(msg)
    else:
        container.success(msg)
    with container.expander("ⓘ 詳細（HMM 学習結果）"):
        container.write(f"判定方法: {result.metadata.calculation_method}")
        container.write(f"学習期間: {result.metadata.training_period}")
        container.write(f"出所: {result.metadata.academic_source}")
```

**テスト**: `to_signal(RegimeResult(...current_regime="Crisis"...))` → 🔴/暴落リスク/新規買い停止

### 3.2 ATR アラートウィジェット — `src/dashboard/widgets/atr_alert.py`

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import pandas as pd

from src.strategies.atr_stop import calculate_trailing_stop


@dataclass(frozen=True)
class AtrAlert:
    """1 銘柄の ATR ストップ判定結果。"""
    ticker: str
    current_price: Decimal
    stop_price: Decimal
    status: Literal["safe", "near", "breach"]   # 安全 / 接近 / 抵触
    reason_lines: tuple[str, ...]               # 規律ベースの根拠


_NEAR_THRESHOLD_PCT = Decimal("0.02")  # ストップ価格の +2% 以内なら "near"


def evaluate_alert(
    ticker: str,
    ohlc: pd.DataFrame,
    current_price: Decimal,
    extra_reasons: tuple[str, ...] = (),
) -> AtrAlert:
    """OHLC + 現在価格 → アラート判定。

    Args:
        ticker: 銘柄
        ohlc: ``high`` / ``low`` / ``close`` カラムを持つ DataFrame
        current_price: 評価時点の現在価格（同一通貨）
        extra_reasons: ホームで追加表示する根拠（Magic Formula スコア低下等）
    """
    stop = calculate_trailing_stop(ohlc)
    if current_price < stop:
        status = "breach"
    elif current_price < stop * (Decimal("1") + _NEAR_THRESHOLD_PCT):
        status = "near"
    else:
        status = "safe"
    return AtrAlert(
        ticker=ticker,
        current_price=current_price,
        stop_price=stop,
        status=status,
        reason_lines=extra_reasons,
    )
```

**規律ベース表現の出力例**（CLAUDE.md §9.3 / §9.5）:
> 🟡 AAPL: ATR トレーリングストップ条件に**接近**（基準 ¥24,500、現在 ¥24,800）。**売却検討**。
> 理由（参考）: ① Magic Formula スコア低下 87→62

**「指示」ではなく「条件到達 + 根拠」で出す**。要件 §3.4 反対意見 4 の遵守。

### 3.3 `01_home.py` への追記

既存コード（取得コストサマリー / 最新価格評価 / 保有銘柄一覧 / リスク警告）は **触らない**。
228 行末尾の前に新セクションを 2 つ追加:

1. **市場信号灯セクション**（1 行 + 折りたたみ）
   - VIX 取得: `EODHDClient.get_eod("VIX", exchange="INDX", from_date=今日-2年)`
   - SPY 取得（市場代表値）: `get_eod("SPY", exchange="US", from_date=今日-2年)`
   - `detect_regime_with_provenance(prices=spy.close, vix=vix.close)` → `render_regime_signal()`
   - 失敗時は `RegimeResult=None` で「判定中」メッセージのフォールバック

2. **ATR アラート行セクション**（保有銘柄ごとに 1 行）
   - 各 holding に対し `EODHDClient.get_eod(ticker, exchange, from_date=今日-90日)` で OHLC 取得
   - `evaluate_alert(ticker, ohlc, current_price_jpy)` で判定
   - status="breach"|"near" の銘柄を上から表示、"safe" は折りたたみ

### 3.4 検証
- ポートフォリオ空でも crash しない（既存の `if len(portfolio.holdings) == 0: st.stop()` の前に信号灯）
- VIX 取得失敗時にフォールバック動作
- pytest 緑

---

## 4. Step 3: おすすめ銘柄刷新（90 分）

### 4.1 `src/data/famous_holdings.py` 新規

```python
"""達人投資家の保有銘柄静的辞書（Phase 3.2 で SEC EDGAR 動的化予定）。

Berkshire Hathaway 13F-HR 2026Q1 等の主要銘柄を手動でメンテ。
"""
from typing import Final

# (ticker, exchange) → frozenset of investor names
FAMOUS_HOLDINGS: Final[dict[tuple[str, str], frozenset[str]]] = {
    ("AAPL", "US"):  frozenset({"Buffett"}),
    ("KO", "US"):    frozenset({"Buffett"}),
    ("AXP", "US"):   frozenset({"Buffett"}),
    ("BAC", "US"):   frozenset({"Buffett"}),
    ("OXY", "US"):   frozenset({"Buffett"}),
    ("RAIN", "US"):  frozenset({"Pabrai"}),
    ("JD", "US"):    frozenset({"Burry"}),
    # 拡張は手動メンテ、Phase 3.2 で SEC EDGAR から動的取得に置換
}


def get_famous_owners(ticker: str, exchange: str) -> frozenset[str]:
    """指定銘柄を保有している達人名集合を返す。未保有時は空集合。"""
    return FAMOUS_HOLDINGS.get((ticker.upper(), exchange.upper()), frozenset())


_INVESTOR_BADGES: Final[dict[str, str]] = {
    "Buffett": "🐋 バフェット保有",
    "Pabrai":  "🐋 パブライ保有",
    "Burry":   "🐋 バーリ保有",
    "Ackman":  "🐋 アックマン保有",
}


def render_owner_badges(owners: frozenset[str]) -> str:
    """達人名集合 → サイドバー表示用バッジ文字列（複数なら空白区切り）。"""
    return " ".join(_INVESTOR_BADGES.get(name, name) for name in sorted(owners))
```

### 4.2 `02_screener.py` 刷新

既存ロジック（Composite Score 計算、Magic Formula）は **流用**。
UI 部分のみ刷新:

```python
# Before: 単一プリセット選択 + Top10 表
# After:  4 カテゴリの tab 表示

categories = {
    "🐋 長期保有 (バフェット型)":   "buffett",     # 既存プリセット
    "📊 中期 (リンチ型)":           "lynch",       # 既存プリセット
    "🚀 短期 (モメンタム)":         "momentum",    # 既存プリセット拡張
    "💎 急騰候補 (逆張り)":         "contrarian",  # 既存プリセット
}
tab_labels = list(categories.keys())
tabs = st.tabs(tab_labels)
for tab, (label, preset_key) in zip(tabs, categories.items()):
    with tab:
        ranking = compute_composite_score(universe, preset=PRESETS[preset_key])
        for row in ranking.head(10).itertuples():
            owners = get_famous_owners(row.ticker, row.exchange)
            badges = render_owner_badges(owners)
            st.markdown(
                f"### {row.ticker} {badges}\n"
                f"**スコア**: {row.composite_score}/100 — "
                f"**理由**: {row.short_rationale}"
            )
            with st.expander("ⓘ 詳細"):
                st.dataframe(row._asdict())
```

### 4.3 「未来予測チャート」要素

各銘柄カード内に「将来予測を見る」ボタン → クリックで `08_research.py` に銘柄パラメータ付きで遷移
（`st.query_params` 経由 or `st.session_state` 経由）。

### 4.4 検証
- 4 タブで切り替えできる
- AAPL 行に "🐋 バフェット保有" バッジが出る（静的辞書ヒット）
- 既存スクリーナーテスト 緑

---

## 5. Step 4: 銘柄リサーチ統合（60 分）

### 5.1 `src/dashboard/pages/08_research.py` 新規

```python
"""銘柄リサーチ — ティッカー入力 → 過去検証 / 将来予測 を内部タブで切替。

既存 04_backtest.py / 05_monte_carlo.py のロジックを
src/dashboard/research/ 配下に関数化したものを呼び出す。
"""
import streamlit as st

from src.dashboard.research.backtest_panel import render_backtest_panel
from src.dashboard.research.monte_carlo_panel import render_monte_carlo_panel
from src.ui.theme import apply_theme

st.set_page_config(page_title="銘柄を調べる — kaori_kabu", page_icon="🧪", layout="wide")
apply_theme()

st.title("🧪 銘柄を調べる")

# 銘柄入力（query params 連携で screener から遷移可能）
default_ticker = st.query_params.get("ticker", "AAPL")
ticker = st.text_input("ティッカー", value=default_ticker)
exchange = st.selectbox("取引所", ["US", "TO"], index=0)

tab_past, tab_future = st.tabs(["📜 過去検証", "🎲 将来予測"])

with tab_past:
    render_backtest_panel(ticker=ticker, exchange=exchange)

with tab_future:
    render_monte_carlo_panel(ticker=ticker, exchange=exchange)
```

### 5.2 既存ページのロジック関数化

`04_backtest.py` / `05_monte_carlo.py` の主要ロジックを以下に抽出:
- `src/dashboard/research/backtest_panel.py` に `render_backtest_panel(ticker, exchange)`
- `src/dashboard/research/monte_carlo_panel.py` に `render_monte_carlo_panel(ticker, exchange)`

旧ページファイルは関数を呼ぶだけの薄いラッパーに変更（Streamlit ナビから外れているが、URL 直接アクセス時のフォールバックとして残す）。

### 5.3 検証
- `/research?ticker=AAPL&exchange=US` で過去/将来タブが描画
- 既存 backtest / monte_carlo テスト 緑

---

## 6. テスト戦略

| Step | 新規テスト | 既存テスト維持 |
|---|---|---|
| 1 | （UI 目視のみ、テスト不要） | 223 件 |
| 2 | `test_regime_signal.py`（5 ケース）+ `test_atr_alert.py`（5 ケース）| 223 件 |
| 3 | `test_famous_holdings.py`（3 ケース：辞書整合性 / バッジ / 未登録） | 223 件 |
| 4 | パネル関数化のリファクタリングのみ。既存ロジックテストは継続 | 223 件 |

**最終目標**: 223 + 約 13 = **236 件以上 GREEN**

各 Step 完了時に必ず:
```bash
export PATH="$HOME/.local/bin:$PATH"
uv run pytest --no-cov -m "not slow" -q | tail -3
```
赤になったら次に進まない。

---

## 7. ロールバック戦略

- Step 単位で git commit を作る（atomic rollback 可能）
- ステアリング ID をコミットメッセージに含める: `feat(ui): ステップ 1 ナビ整理 [20260509-ui-5tab-redesign]`
- 万一の crash は `git revert <commit>` で元に戻る
- データ層（regime / atr_stop / composite）には**一切触らない**ので、ロールバックは UI 層のみで完結

---

## 8. CLAUDE.md 規約遵守確認

| 規約 | 適用箇所 |
|---|---|
| §9.1 数値は Decimal | `evaluate_alert` の `current_price` / `stop_price` |
| §9.3 一本線予測禁止 | Monte Carlo は確率分布タブで表示 |
| §9.4 シグナルに根拠併記 | ATR アラートの `reason_lines` |
| §9.5 損切り規律 | ATR ストップ抵触を Decision Log 記録（Step 2 で hook 検討） |
| §9.7 認知バイアス警告 | 信号灯 = Recency Bias 抑止、ATR = Loss Aversion 抑止 |
| §9.8.2 計算メタデータ | `regime.py` の `RegimeMetadata` 既存活用 |
| 1 ファイル毎承認ゲート | tasklist.md の各サブタスクで都度確認 |

---

## 9. 次に書く: `tasklist.md`

実装の細かいチェックリスト（4 Step × 数サブタスク）を `tasklist.md` に展開。
承認後、tasklist 通りに 1 ファイル毎ゲートで進行。
