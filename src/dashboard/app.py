"""kaori_kabu Streamlit ダッシュボード — エントリーポイント。

起動方法:
    streamlit run src/dashboard/app.py
    または
    kabu-dashboard  (pyproject.toml の scripts 経由)
"""

from __future__ import annotations

import streamlit as st

from src.config.settings import settings
from src.ui.theme import apply_theme


def main() -> None:
    """Streamlit アプリのエントリーポイント。"""
    st.set_page_config(
        page_title="kaori_kabu — 個人株運用ダッシュボード",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()

    # サイドバー
    with st.sidebar:
        st.title("📈 kaori_kabu")
        st.caption("世界トップ投資家の手法を AI で再現")
        st.divider()

        st.subheader("⚙️ API 設定状況")
        api_status = {
            "EODHD": bool(settings.eodhd_api_key),
            "J-Quants": bool(settings.jquants_refresh_token),
            "SEC EDGAR": bool(settings.sec_edgar_user_agent),
            "FRED": bool(settings.fred_api_key),
        }
        for name, configured in api_status.items():
            icon = "✅" if configured else "❌"
            st.write(f"{icon} {name}")

        if not all(api_status.values()):
            st.warning("未設定の API キーがあります。`.env` を編集してください。")

        st.divider()
        st.caption(f"環境: {settings.app_env}")
        st.caption(f"ベース通貨: {settings.base_currency}")

    # メインエリア
    st.title("📈 kaori_kabu — 個人株運用ダッシュボード")
    st.markdown(
        """
        > 世界トップ投資家の手法を AI で再現し、規律と統計で勝つ個人ローカルツール。

        **完全に個人専用ローカル運用**（金商法対象外、投資助言サービスではない、
        すべて自己責任で売買判断）。
        """
    )

    st.subheader("🎯 MVP 7 機能")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            1. **Magic Formula スクリーナー** — Greenblatt のバリュー戦略
            2. **13F Cloning** — Berkshire / Pabrai / Burry / Ackman 追従
            3. **Monte Carlo 確率分布** — 1000 パス GBM
            4. **Half-Kelly ポジションサイザー** — 数学的最適 × 0.5
            """
        )
    with col2:
        st.markdown(
            """
            5. **リスク指標** — Sharpe / Sortino / VaR / CVaR
            6. **HMM レジーム検出** — Bull / Choppy / Crisis
            7. **ATR トレーリングストップ** — Loss Aversion 対策
            """
        )

    st.divider()

    st.subheader("📂 ページ")
    st.info(
        "サイドバーの **Pages** から各機能ページに遷移できます。\n\n"
        "未実装の機能は順次追加されます。"
    )

    st.divider()
    with st.expander("⚠️ 免責事項"):
        st.markdown(
            """
            - 本ツールは個人専用の調査・分析支援であり、**投資助言ではない**
            - 売買判断はすべて自己責任で実施
            - 表示される確率分布・シグナルは過去データに基づく統計的推定であり、
              将来を保証しない
            - API データ提供元の遅延・誤り・規約変更により結果が変動する
            - 損失について本ツールは一切の責任を負わない
            """
        )


if __name__ == "__main__":
    main()
