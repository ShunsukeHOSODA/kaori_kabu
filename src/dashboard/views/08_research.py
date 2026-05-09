"""銘柄リサーチ — ティッカー入力 → 過去検証 / 将来予測 を内部タブで切替。

Phase 3.2 Step 4 で実装予定（要件 .steering/20260509-ui-5tab-redesign/）。
現状はプレースホルダで、04_backtest.py / 05_monte_carlo.py への誘導のみ。
"""

from __future__ import annotations

import streamlit as st

from src.ui.theme import apply_theme

st.set_page_config(
    page_title="銘柄を調べる — kaori_kabu", page_icon="🧪", layout="wide"
)
apply_theme()

st.title("🧪 銘柄を調べる")
st.caption(
    "気になるティッカーを入力すると、過去成績（戦略を過去で回した結果）と"
    "将来予測（モンテカルロ確率分布）を内部タブで切り替えて確認できます。"
)

st.info(
    "🚧 **このページは現在実装中です**（Phase 3.2 Step 4 で完成予定）。\n\n"
    "現時点では、過去検証は内部の `04_backtest.py`、"
    "将来予測は `05_monte_carlo.py` のロジックを統合する計画です。"
)

with st.expander("ⓘ 計画"):
    st.markdown(
        """
        ### 完成時の構成
        1. **ティッカー入力欄** — 気になる銘柄のシンボルを入力（例 `AAPL`、`7203`）
        2. **取引所選択** — `US` / `TO` 等
        3. **内部タブ**
            - 📜 **過去検証**: 戦略バックテスト（vectorbt）+ 性能指標（11 指標）
            - 🎲 **将来予測**: モンテカルロ法 1000 パスの確率分布（5/25/50/75/95 パーセンタイル）

        ### 進捗
        - [x] ステアリング doc 作成
        - [x] ナビゲーション組込み
        - [ ] バックテストパネル関数化
        - [ ] モンテカルロパネル関数化
        - [ ] ティッカー入力 + タブ切替 UI 統合
        """
    )
