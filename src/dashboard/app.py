"""kaori_kabu Streamlit ダッシュボード — エントリーポイント。

起動方法:
    streamlit run src/dashboard/app.py
    または
    kabu-dashboard  (pyproject.toml の scripts 経由)

ナビゲーション設計:
    Streamlit 1.36+ の :func:`st.navigation` を採用してサイドバーラベルを
    日本語明示。ファイル名は英語のまま (`01_home.py` 等) なので URL
    (``/home``, ``/screener`` 等) も英語維持されつつ、ブラウザ自動翻訳
    （Chrome の "Home → 家", "Thirteen F → 13人の" 等）の発火源を消す。
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config.settings import settings
from src.ui.theme import apply_theme

# ビューファイルへのパス（views/ 配下を絶対パス指定）。
# `pages/` という名前にすると Streamlit の自動探索が st.navigation を上書きして
# 8 ページすべてサイドバーに出てしまうため、`views/` にリネームして抑止する
# （要件 .steering/20260509-ui-5tab-redesign/）。
_PAGES_DIR: Path = Path(__file__).parent / "views"


def _welcome_page() -> None:
    """デフォルトの「ようこそ」ページ — MVP 7 機能の概要と免責事項。"""
    st.title("📈 kaori_kabu — 個人株運用ダッシュボード")
    st.markdown(
        """
        > 世界トップ投資家の手法を AI で再現し、規律と統計で勝つ個人ローカルツール。

        **完全に個人専用ローカル運用**（金商法対象外、投資助言サービスではない、
        すべて自己責任で売買判断）。
        """
    )

    st.subheader("🎯 裏で動く 7 つの統計手法")
    st.caption(
        "下記はすべて Claude が**裏で**実行し、結果だけを 🏠 ホーム / 🔍 おすすめ銘柄 / "
        "🧪 銘柄を調べる に統合表示します。個別タブで触る必要はありません。"
    )
    # ブラウザ自動翻訳が固有名詞を「グリーンブラット」「バークシャー」等と
    # 翻訳して可読性を破壊するため、英語の人名・社名は `translate="no"` で
    # 囲み、日本語の説明文と分離する。
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            1. **割安銘柄スクリーナー** — <span translate="no">Greenblatt</span> のマジックフォーミュラで割安株を抽出
            2. **達人投資家追従（13F）** — <span translate="no">Berkshire / Pabrai / Burry / Ackman</span> の四半期保有銘柄を真似
            3. **将来シミュレーション** — モンテカルロ法で 1000 通りの未来パスを描画
            4. **半ケリー法ポジションサイザー** — 数学的最適サイズ × 0.5（破滅回避）
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """
            5. **リスク指標** — <span translate="no">Sharpe / Sortino / VaR / CVaR</span>（リスク対比リターン）
            6. **市場レジーム検出（HMM）** — 強気 / 横ばい / 暴落 を統計的に判定
            7. **<span translate="no">ATR</span> トレーリングストップ** — 含み損で焦って売る癖を機械化で防ぐ
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("🗺️ サイドバーの使い方")
    st.caption(
        "左メニューの各ページが「何をするためのもの」かを一覧で示します。"
        "用語が分からなくても、目的（やりたいこと）から選べる構成です。"
    )

    # 5 タブの役割・使うタイミング・素人向け補足を 1 行ずつ
    st.markdown(
        """
        | メニュー | 何ができる？ | こんな時に使う |
        |---|---|---|
        | 🏠 **ホーム** | 保有銘柄の評価額・含み損益・**市場の機嫌（信号灯）**・**利確 / 損切りアラート** | 朝イチで「今いくら？売り時？」を見たい時 |
        | 🔍 **おすすめ銘柄** | <span translate="no">Claude</span> が裏で<span translate="no">Greenblatt</span> + 達人追従（13F）+ マクロ環境 を統合し、**長期 / 中期 / 短期 / 急騰候補** の 4 カテゴリで推薦 | 新しい買い候補を探したい時 |
        | 🧪 **銘柄を調べる** | 気になるティッカーを入力 → **過去検証**（戦略を過去で回した成績）と **将来予測**（モンテカルロ確率分布）を内部タブで切替 | 個別銘柄を深掘りしたい時 |
        | ⚙️ **設定** | <span translate="no">API</span> 設定状況・戦略パラメータ・キャッシュ <span translate="no">TTL</span>・口座種別 | 環境を確認したい時 |
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "📌 まずは **🏠 ホーム** で保有銘柄と市場の機嫌を確認、"
        "次に **🔍 おすすめ銘柄** で新候補を見つける流れがおすすめです。"
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


def _render_sidebar_status() -> None:
    """サイドバー上部の API 設定状況パネル（全ページ共通）。"""
    with st.sidebar:
        st.title("📈 kaori_kabu")
        st.caption("世界トップ投資家の手法を AI で再現")
        st.divider()

        st.subheader("⚙️ API 設定状況")
        # 英語の API 名（FRED, EODHD 等）は Chrome 自動翻訳が
        # 「フレッド」等と勝手に日本語化してしまうので、translate="no" で守る。
        api_status = {
            "EODHD": bool(settings.eodhd_api_key),
            "J-Quants": bool(settings.jquants_refresh_token),
            "SEC EDGAR": bool(settings.sec_edgar_user_agent),
            "FRED": bool(settings.fred_api_key),
        }
        for name, configured in api_status.items():
            icon = "✅" if configured else "❌"
            st.markdown(
                f"{icon} <span translate='no'>{name}</span>",
                unsafe_allow_html=True,
            )

        if not all(api_status.values()):
            st.warning("未設定の API キーがあります。`.env` を編集してください。")

        st.divider()
        st.caption(f"環境: {settings.app_env}")
        st.caption(f"ベース通貨: {settings.base_currency}")


def main() -> None:
    """Streamlit アプリのエントリーポイント。

    :func:`st.navigation` で **日本語ラベル + 英語 URL** のサイドバーを構築。
    各ページの ``st.set_page_config`` はそのまま動作する（個別ページタイトル・
    アイコン制御はページ側、ナビゲーションラベルはここで明示）。
    """
    apply_theme()
    _render_sidebar_status()

    # 5 タブ構成（要件 .steering/20260509-ui-5tab-redesign/）。
    # 13F / マクロ / 過去検証 / 将来予測 はナビ非表示。Claude が裏で
    # おすすめ銘柄計算 / 信号灯 / 銘柄リサーチ統合に使用。ファイルは温存。
    # url_path は英語維持で Chrome 自動翻訳の発火源を抑える。
    pages = [
        st.Page(_welcome_page, title="📈 ようこそ", default=True),
        st.Page(
            str(_PAGES_DIR / "01_home.py"),
            title="🏠 ホーム",
            url_path="home",
        ),
        st.Page(
            str(_PAGES_DIR / "02_screener.py"),
            title="🔍 おすすめ銘柄",
            url_path="screener",
        ),
        st.Page(
            str(_PAGES_DIR / "08_research.py"),
            title="🧪 銘柄を調べる",
            url_path="research",
        ),
        st.Page(
            str(_PAGES_DIR / "07_settings.py"),
            title="⚙️ 設定",
            url_path="settings",
        ),
    ]
    pg = st.navigation(pages, position="sidebar")
    pg.run()


if __name__ == "__main__":
    main()
