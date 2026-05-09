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

# ページファイルへのパス（pages/ ディレクトリ配下を絶対パス指定）
_PAGES_DIR: Path = Path(__file__).parent / "pages"


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

    st.subheader("🎯 MVP 7 機能")
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

    # 各サイドバー項目の役割・使うタイミング・素人向け補足を 1 行ずつ
    st.markdown(
        """
        | メニュー | 何ができる？ | こんな時に使う |
        |---|---|---|
        | 🏠 **ホーム** | 保有銘柄一覧と現在価格での評価額・含み損益を確認 | 朝イチで「今いくら？」を見たい時 |
        | 📊 **割安銘柄探し** | <span translate="no">Greenblatt</span> のマジックフォーミュラ（資本効率 × 割安度）で世界の割安株 Top 10 を抽出 | 新しい買い候補を探したい時 |
        | 🐋 **達人追従（13F）** | <span translate="no">Berkshire (Buffett) / Pabrai / Burry / Ackman</span> など著名投資家の四半期保有銘柄を SEC から取得 | 「あのプロは今何を持ってる？」を確認 |
        | 🔬 **過去検証** | 自分の戦略（割安株保有・配当再投資など）を過去データで「もし当時やってたら」を計算 | 戦略の有効性を確かめたい時 |
        | 🎲 **将来予測** | モンテカルロ法で 1000 通りの未来の値動きを確率分布として描画（「絶対 + ○ 円」予測は禁止） | 「1 年後にいくらになる確率？」を知りたい時 |
        | 🌍 **マクロ経済** | <span translate="no">Fed</span> 利上げ確率（予測市場）、米景気指標、市場レジーム判定 | 相場全体の温度感を見たい時 |
        | ⚙️ **設定** | <span translate="no">API</span> キー設定状況、戦略パラメータ、キャッシュ <span translate="no">TTL</span> | データ源や閾値の確認 |
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "📌 まずは **🏠 ホーム** で保有銘柄の評価から、"
        "次に **📊 割安銘柄探し** で新候補を見つける流れがおすすめです。"
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

    # icon は title 内の emoji を採用（重複表示回避）。url_path は英語維持で
    # Chrome 翻訳の発火源を抑え、default page (welcome) は root `/` のみ。
    pages = [
        st.Page(_welcome_page, title="📈 ようこそ", default=True),
        st.Page(
            str(_PAGES_DIR / "01_home.py"),
            title="🏠 ホーム",
            url_path="home",
        ),
        st.Page(
            str(_PAGES_DIR / "02_screener.py"),
            title="📊 割安銘柄探し",
            url_path="screener",
        ),
        st.Page(
            str(_PAGES_DIR / "03_thirteen_f.py"),
            title="🐋 達人追従（13F）",
            url_path="thirteen-f",
        ),
        st.Page(
            str(_PAGES_DIR / "04_backtest.py"),
            title="🔬 過去検証",
            url_path="backtest",
        ),
        st.Page(
            str(_PAGES_DIR / "05_monte_carlo.py"),
            title="🎲 将来予測",
            url_path="monte-carlo",
        ),
        st.Page(
            str(_PAGES_DIR / "06_macro.py"),
            title="🌍 マクロ経済",
            url_path="macro",
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
