"""Magic Formula スクリーナー — Greenblatt のバリュー戦略 + 推奨根拠カード。

CLAUDE.md §9.3 / §9.4 / §9.8 に準拠:
    - 一本線予測禁止（ランキング合算スコアで提示）
    - シグナル根拠併記（学術的バックボーン引用 + リスク警告）
    - Provenance metadata を ⓘ で開示

データソース:
    - **Demo**: 米国大型株 10 銘柄の合成データ（API キー不要）
    - **EODHD ライブ**: ``settings.eodhd_api_key`` ありで有効。ティッカーを
      指定するとファンダメンタルを取得して Magic Formula を計算する。
      取得結果は TTL 7 日でローカルキャッシュ（CLAUDE.md §9.2）。

Phase 5.5.0 構造（handoff-session-6 §5.1 / Phase 5.4.4 C-H-2 解消）:
    - 本ファイル: ページエントリ + サイドバー UI + 制御フロー + BUY フォーム
    - ``_screener_compute.py``: run_button 経路の計算ロジック
    - ``_screener_display.py``: 計算済みデータの描画専用
    - ``_screener_session.py``: ScreeningSession (frozen dataclass)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import streamlit as st

from src.config.settings import settings
from src.dashboard.views._screener_compute import (
    parse_tickers,
    run_screening_pipeline,
)
from src.dashboard.views._screener_display import (
    TOP_PICKS_FOR_NEWS,
    render_screening_results,
)
from src.dashboard.views._screener_session import ScreeningSession
from src.data.cache import ParquetCache
from src.data.eodhd import EODHDClient
from src.data.financedatabase_client import get_jp_universe
from src.data.news import NewsClient
from src.data.yfinance import YFinanceClient, make_default_yfinance_client
from src.portfolio.buy_decision import (
    BuyOrderRequest,
    ScreenerTrigger,
    submit_buy_order,
)
from src.ui.theme import apply_theme

st.set_page_config(
    page_title="おすすめ銘柄 — kaori_kabu", page_icon="🔍", layout="wide"
)
apply_theme()

st.title("🔍 おすすめ銘柄")
st.caption(
    "Magic Formula + 7 軸 Composite Score + 達人保有（13F）+ モメンタム を統合し、"
    "**長期 / 中期 / 短期 / 急騰候補** の 4 カテゴリで推薦"
)

st.markdown(
    """
    > **Magic Formula = ROC ランキング + Earnings Yield ランキング**

    良い会社（ROC 高）を安く買う（EY 高）— Buffett 哲学を数式に落としたもの。
    Greenblatt 2010 のバックテストで年率 17% を実証。
    上位銘柄は Composite Score（7 軸）と達人保有バッジ 🐋 で更に絞り込む。
    """
)


# ---------------------------------------------------------------------------
# Streamlit client factories（同セッション内シングルトン化）
# ---------------------------------------------------------------------------


@st.cache_data(ttl=604800, show_spinner="🇯🇵 TSE 銘柄リスト取得中...")
def _get_jp_universe_cached(cap_filter: str, limit: int) -> list[str]:
    """FinanceDatabase から JP ユニバース取得（7d キャッシュ、§4.5）。

    Streamlit `@st.cache_data` 経由で同セッション内の重複取得を抑止。
    """
    return get_jp_universe(cap_filter=cap_filter, limit=limit)  # type: ignore[arg-type]


@st.cache_resource
def get_eodhd_client() -> EODHDClient | None:
    """``EODHD_API_KEY`` がある場合のみ EODHDClient を生成。

    EOD 価格（Momentum 用）に使う。Fundamentals は別契約のため yfinance に
    委譲する（CLAUDE.md §5 のコスト最小化方針）。

    Streamlit の :func:`st.cache_resource` で session 中シングルトン化。
    キーが空なら ``None`` を返し、UI 側で Demo にフォールバックさせる。
    """
    if not settings.eodhd_api_key:
        return None
    cache = ParquetCache(base_dir=settings.cache_dir)
    return EODHDClient(api_key=settings.eodhd_api_key, cache=cache)


@st.cache_resource
def get_yfinance_client() -> YFinanceClient:
    """yfinance ベースのファンダメンタルクライアント（無料・無設定）。

    Yahoo Finance の非公式 API を使ってファンダを取得。米国大型株は十分、
    日本株は欠損があり得るので J-Quants Light 併用が望ましい（Phase 3.2）。
    """
    cache = ParquetCache(base_dir=settings.cache_dir)
    return make_default_yfinance_client(cache)


@st.cache_resource
def get_news_client() -> NewsClient | None:
    """Tavily/Exa キーが揃っているときだけ NewsClient を生成（Phase 2）。"""
    if not settings.tavily_api_key or not settings.exa_api_key:
        return None
    cache = ParquetCache(base_dir=settings.cache_dir)
    return NewsClient(
        tavily_api_key=settings.tavily_api_key,
        exa_api_key=settings.exa_api_key,
        cache=cache,
    )


@st.cache_resource
def get_anthropic_client():  # noqa: ANN201 — anthropic.Anthropic を返す
    """``ANTHROPIC_API_KEY`` があるときだけ Anthropic クライアント生成。"""
    if not settings.anthropic_api_key:
        return None
    import anthropic  # noqa: PLC0415 — オプショナル機能の lazy import

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ---------------------------------------------------------------------------
# サイドバー UI
# ---------------------------------------------------------------------------


eodhd_client = get_eodhd_client()
yfinance_client = get_yfinance_client()
api_available = eodhd_client is not None
news_client = get_news_client()
anthropic_client = get_anthropic_client()
news_features_available = (
    news_client is not None and anthropic_client is not None
)

with st.sidebar:
    st.subheader("データソース")
    if api_available:
        source_mode = st.radio(
            "モード",
            ["EODHD ライブ", "Demo（合成 10 銘柄）"],
            index=0,
            help="EODHD ライブはファンダ TTL 7 日キャッシュ経由で API 消費を抑制",
        )
    else:
        source_mode = "Demo（合成 10 銘柄）"
        st.warning(
            "⚠️ `EODHD_API_KEY` が未設定のため Demo モードのみ利用可。"
            "実銘柄スクリーニングには `.env` に EODHD_API_KEY を設定してください。"
        )

    st.subheader("パラメータ")
    real_mode = source_mode == "EODHD ライブ"

    exchange = st.selectbox(
        "取引所",
        ["US", "TO"],
        index=0,
        disabled=not real_mode,
        help="US=米国、TO=東証（日本株）。東証は yfinance 経由で `.T` 形式に自動変換",
    )

    # 取引所別デフォルトティッカー（時価総額上位 + Magic Formula 候補のミックス）
    # 米国: GAFAM + 高 ROC 候補。日本: TOPIX Core30 から自動車/技術/消費者向け代表
    _DEFAULT_TICKERS_US = (
        "AAPL, MSFT, GOOGL, AMZN, META, NVDA, JNJ, PG, KO, WMT"
    )
    _DEFAULT_TICKERS_JP = (
        "7203, 6758, 9984, 6861, 6098, 8035, 4063, 6981, 7974, 8001"
    )

    # JP ユニバース 動的選択（§4.5、handoff-phase4.md）— TO モード時のみ
    _JP_UNIVERSE_LABELS: dict[str, tuple[str, int] | None] = {
        "プリセット 10 銘柄（Core30 抜粋）": None,
        "Large+ Cap（TOPIX 100 近似、~96 銘柄）": ("large", 100),
        "Mid+ Cap（TOPIX 500 近似、~350 銘柄）": ("mid", 300),
    }
    _jp_universe_label: str = "プリセット 10 銘柄（Core30 抜粋）"
    if real_mode and exchange == "TO":
        _jp_universe_label = st.selectbox(
            "JP ユニバース",
            options=list(_JP_UNIVERSE_LABELS.keys()),
            index=0,
            help=(
                "FinanceDatabase (無料) から TSE 銘柄を時価総額カテゴリ別に動的取得。"
                "TOPIX 公式分類とは厳密に対応しないが、米国基準 Mega/Large/Mid Cap を"
                "用いて近似。キャッシュ 7d で API 呼び出しを抑制。"
            ),
        )

    if real_mode:
        if exchange == "TO":
            _jp_filter_spec = _JP_UNIVERSE_LABELS[_jp_universe_label]
            if _jp_filter_spec is None:
                _default = _DEFAULT_TICKERS_JP
            else:
                _cap_filter, _limit = _jp_filter_spec
                try:
                    _jp_tickers = _get_jp_universe_cached(_cap_filter, _limit)
                    _default = ", ".join(_jp_tickers) if _jp_tickers else _DEFAULT_TICKERS_JP
                except Exception as exc:  # noqa: BLE001 — UI fallback
                    st.warning(
                        f"⚠️ FinanceDatabase 取得失敗 ({type(exc).__name__})。"
                        "プリセットにフォールバック"
                    )
                    _default = _DEFAULT_TICKERS_JP
        else:
            _default = _DEFAULT_TICKERS_US

        if exchange == "TO":
            st.caption(
                "🇯🇵 東証選択中: 4 桁証券コードで入力（例: 7203 = トヨタ）。"
                "yfinance が `.T` 付きで取得します。"
            )
        # JP universe selectbox 切替時に textarea を再描画させる key
        _ticker_key = (
            f"ticker_input_{exchange}_{_jp_universe_label}"
            if exchange == "TO"
            else f"ticker_input_{exchange}"
        )
        ticker_text = st.text_area(
            "ティッカー（カンマまたは改行区切り）",
            value=_default,
            height=120,
            key=_ticker_key,
        )
        tickers = parse_tickers(ticker_text)
        st.caption(f"対象 {len(tickers)} 銘柄")
    else:
        tickers = []

    min_market_cap = st.number_input(
        "最低時価総額 (USD)",
        value=settings.mf_min_market_cap_usd,
        step=10_000_000,
        disabled=not real_mode,
    )
    _SECTOR_LABEL_JP: dict[str, str] = {
        "Financials": "金融（Financials）",
        "Utilities": "公益事業（Utilities）",
        "Energy": "エネルギー（Energy）",
        "Real Estate": "不動産（Real Estate）",
    }
    excluded = st.multiselect(
        "除外セクター",
        list(_SECTOR_LABEL_JP.keys()),
        default=settings.excluded_sectors_list,
        format_func=lambda s: _SECTOR_LABEL_JP.get(s, s),
        disabled=not real_mode,
        help="Magic Formula は資本回転率の異なる金融・公益・エネルギーを除外するのが定石。",
    )

    top_n = st.slider("表示件数（上位）", 1, 30, min(settings.mf_top_n, 30))

    st.subheader("📰 推奨根拠カード")
    if news_features_available:
        enable_news_cards = st.checkbox(
            f"上位 {TOP_PICKS_FOR_NEWS} 銘柄を自動分析",
            value=True,
            help=(
                "Tavily/Exa で 4 系統ニュース取得 + Buffett-Munger と Burry "
                "レンズ + Claude Haiku でセンチメント分析。"
                "「なぜ推すか」を結果テーブル直下のカードに表示。"
            ),
        )
    else:
        enable_news_cards = False
        missing: list[str] = []
        if news_client is None:
            missing.append("`TAVILY_API_KEY` & `EXA_API_KEY`")
        if anthropic_client is None:
            missing.append("`ANTHROPIC_API_KEY`")
        st.caption(
            "ℹ️ 推奨根拠カードを有効化するには `.env` または `~/.claude/.env` に "
            + " と ".join(missing)
            + " を設定。"
        )

    st.subheader("📋 Composite Score")
    enable_composite = st.checkbox(
        "上位銘柄に総合スコア（7 軸）を併記する",
        value=True,
        help=(
            "Quality / Value / Income / Growth / Risk / Momentum / Sentiment の"
            "7 軸を、投資スタイル別プリセットで重み付け合算した総合スコア。"
            "配当・破綻リスク・センチメントなど、見落としがちな観点を一画面で確認できる。"
        ),
        disabled=not real_mode,
    )
    if enable_composite and real_mode:
        # 要件 .steering/20260509-ui-5tab-redesign/ §4: 4 カテゴリ表示
        # （長期 / 中期 / 短期 / 急騰候補）。配当再投資型は Composite ロジック
        # としては有効だが、おすすめ UI では 4 カテゴリに絞る。
        _CATEGORY_TO_PRESET: dict[str, str] = {
            "🐋 長期保有 (バフェット型)": "Buffett_型_暫定",
            "📊 中期 (リンチ型)": "Lynch_型",
            "🚀 短期 (モメンタム)": "モメンタム型",
            "💎 急騰候補 (逆張り)": "逆張り型",
        }
        _selected_category = st.radio(
            "おすすめカテゴリ",
            options=list(_CATEGORY_TO_PRESET.keys()),
            index=0,
            help=(
                "**4 カテゴリの違い**\n"
                "- 🐋 **長期**: 質×価値、Berkshire 流の長期ホールド型\n"
                "- 📊 **中期**: 成長株 + PEG ≦ 1、テンバガー候補（3-5 年）\n"
                "- 🚀 **短期**: 12m + 1m モメンタム加速、数ヶ月スパン\n"
                "- 💎 **急騰候補**: 深割安 + リスク回避、暴落からの反発狙い"
            ),
        )
        composite_preset = _CATEGORY_TO_PRESET[_selected_category]
    else:
        composite_preset = "Buffett_型_暫定"

    # ───────────────────────────────────────────────
    # 📐 Half-Kelly 推奨サイズ（§4.2 #3、handoff-phase4.md）
    # ───────────────────────────────────────────────
    st.subheader("📐 Half-Kelly 推奨")
    portfolio_value_jpy_input = st.number_input(
        "ポートフォリオ評価額 (JPY)",
        min_value=100_000,
        max_value=1_000_000_000,
        value=1_000_000,
        step=100_000,
        help=(
            "Half-Kelly でポジション推奨を計算する基準額。"
            "Composite Score テーブルに「Kelly推奨JPY」列を併記。"
            "Overconfidence 対策で 5% 上限キャップ済。"
        ),
        disabled=not (enable_composite and real_mode),
    )

    run_button = st.button(
        "🚀 スクリーニング実行",
        type="primary",
        disabled=real_mode and len(tickers) == 0,
    )


# ---------------------------------------------------------------------------
# 制御フロー: run_button 経路 + session_state 経路
# ---------------------------------------------------------------------------
#
# run_button 経路で ScreeningSession を構築 → session_state に格納 → 描画。
# session_state 経路 (BUY フォーム submit 後の rerun) では計算済み
# ScreeningSession を取り出して描画のみ再実行（§12.3 解消）。
# ---------------------------------------------------------------------------


if run_button:
    session: ScreeningSession = run_screening_pipeline(
        tickers=tickers,
        real_mode=real_mode,
        exchange=exchange,
        excluded=excluded,
        min_market_cap=min_market_cap,
        top_n=top_n,
        enable_news_cards=enable_news_cards,
        enable_composite=enable_composite,
        composite_preset=composite_preset,
        portfolio_value_jpy_input=portfolio_value_jpy_input,
        eodhd_client=eodhd_client,
        yfinance_client=yfinance_client,
        news_client=news_client,
        anthropic_client=anthropic_client,
    )
    st.session_state["screening_session"] = session
    render_screening_results(session)
elif "screening_session" in st.session_state:
    # §12.3 解消: BUY フォーム submit 後の rerun 経路（run_button == False）
    # 計算済み ScreeningSession を session_state から取り出して再描画する。
    render_screening_results(st.session_state["screening_session"])


# ---------------------------------------------------------------------------
# 🛒 BUY フォーム（ScreeningSession から取り出し、§4.2 #3 / handoff-phase4.md §11.3）
# ---------------------------------------------------------------------------


if "screening_session" in st.session_state:
    session_for_buy: ScreeningSession = st.session_state["screening_session"]

    # 直近 BUY 結果（前回の rerun 経由でセットされたメッセージを表示）
    if "last_buy_result" in st.session_state:
        st.success(st.session_state["last_buy_result"]["message"])

    st.markdown("---")
    st.subheader("🛒 BUY 記録 — Decision Log に追記")
    st.caption(
        "Composite Score テーブルから 1 銘柄選んで Decision Log (JSONL) に記録。"
        "Kelly 推奨を初期値、上書き可。注文額が Kelly 上限を超えると警告（§9.7）。"
    )

    _ticker_to_row = {row["_ticker_raw"]: row for row in session_for_buy.composite_rows}

    with st.form(key="buy_order_form"):
        form_cols = st.columns([2, 1, 1, 3])
        with form_cols[0]:
            buy_ticker = st.selectbox(
                "銘柄",
                options=list(_ticker_to_row.keys()),
                help="Composite Score テーブルから選択（バッジ除去後の raw ticker）",
            )

        _selected_row = _ticker_to_row[buy_ticker]
        _kelly_size_jpy = int(
            _selected_row["Kelly推奨JPY"]
            .replace("¥", "")
            .replace(",", "")
        )

        with form_cols[1]:
            buy_price_jpy = st.number_input(
                "株価 (JPY)",
                min_value=1,
                value=25_000,
                step=100,
                help="現在の取引価格を JPY で入力",
            )

        # Kelly 推奨額 ÷ 株価 を初期株数の暫定値（最低 1 株）
        _default_shares = max(
            1, _kelly_size_jpy // max(int(buy_price_jpy), 1)
        )

        with form_cols[2]:
            buy_shares = st.number_input(
                "株数",
                min_value=1,
                value=_default_shares,
                step=1,
                help=(
                    f"Kelly 推奨額 ¥{_kelly_size_jpy:,} ÷ 株価 から"
                    "自動算出。上書き可（超過時は警告表示）"
                ),
            )

        with form_cols[3]:
            buy_rationale = st.text_input(
                "追加根拠（任意）",
                placeholder="例: 長期保有候補、決算良好",
                help="Composite Score + プリセットは自動付与、その他根拠を記入",
            )

        submit_buy = st.form_submit_button(
            "✅ BUY 確定（Decision Log に追記）",
            type="primary",
        )

    if submit_buy:
        _order_amount = int(buy_shares) * int(buy_price_jpy)
        _exceeds_kelly = _order_amount > _kelly_size_jpy

        # Overconfidence バイアス対策警告（CLAUDE.md §9.7）
        if _exceeds_kelly:
            st.warning(
                f"⚠️ 注文額 ¥{_order_amount:,} が Kelly 上限 "
                f"¥{_kelly_size_jpy:,} を超過（+¥{_order_amount - _kelly_size_jpy:,}）。"
                "それでも記録します（Overconfidence バイアス監視、§9.7）。"
            )

        _sub_scores_dec = {
            k: Decimal(_selected_row[k])
            for k in ("Q", "V", "I", "G", "R", "M", "S")
            if k in _selected_row
        }

        # Phase 5.4.3: 該当 ticker の Claude 判定を抽出。Sonnet 縮退時は None。
        claude_rank_dict: dict[str, Any] | None = None
        if (
            session_for_buy.ranking_results is not None
            and session_for_buy.signal_bundles is not None
        ):
            for _result, _bundle in zip(
                session_for_buy.ranking_results,
                session_for_buy.signal_bundles,
                strict=True,
            ):
                if _bundle.ticker == buy_ticker:
                    claude_rank_dict = _result.model_dump(mode="json")
                    break

        _buy_request = BuyOrderRequest(
            ticker=buy_ticker,
            shares=Decimal(str(int(buy_shares))),
            price_jpy=Decimal(str(int(buy_price_jpy))),
            trigger=ScreenerTrigger(
                skill="composite-score-screener",
                preset=session_for_buy.composite_preset,
                composite_score=Decimal(_selected_row["Composite"]),
                sub_scores=_sub_scores_dec,
                screener_run_at=session_for_buy.calculated_at_iso,
            ),
            kelly_params=session_for_buy.kelly_params_default,
            portfolio_value_jpy=session_for_buy.portfolio_value_jpy_dec,
            additional_rationale=buy_rationale or "",
            code_commit=session_for_buy.code_commit,
            claude_ranking=claude_rank_dict,
        )

        _log_path = submit_buy_order(
            _buy_request, log_dir=settings.decision_log_dir
        )
        _kelly_status = (
            "✅ 範囲内" if not _exceeds_kelly else "⚠️ 上限超過"
        )
        # Phase 5.4.3: Claude 判定の有無を success メッセージに反映
        _claude_status = (
            f"🤖 Claude スコア: {claude_rank_dict['ranking_score']}/100"
            if claude_rank_dict is not None
            else "🤖 Claude 判定: 縮退中"
        )
        _success_msg = (
            f"✅ **BUY 記録完了**\n\n"
            f"- 銘柄: `{buy_ticker}` × {int(buy_shares)} 株 "
            f"× ¥{int(buy_price_jpy):,} = **¥{_order_amount:,}**\n"
            f"- Composite: {_selected_row['Composite']}/100 "
            f"（{session_for_buy.composite_preset}）\n"
            f"- Kelly 推奨: ¥{_kelly_size_jpy:,} / 実発注: "
            f"¥{_order_amount:,} （{_kelly_status}）\n"
            f"- {_claude_status}\n"
            f"- 📁 JSONL: `{_log_path}`"
        )
        st.success(_success_msg)
        # 次回 rerun でも表示できるよう session_state に保存
        st.session_state["last_buy_result"] = {"message": _success_msg}

else:
    # screening_session が未生成 (= 初回起動 or セッションリセット直後) の案内
    st.info("左サイドバーでパラメータを設定し「スクリーニング実行」を押してください。")


# ---------------------------------------------------------------------------
# 学習 expander
# ---------------------------------------------------------------------------


st.divider()
with st.expander("📚 Magic Formula について（学習）"):
    st.markdown(
        """
        ### なぜ ROC と Earnings Yield の組み合わせ？

        - **ROC（Return on Capital）= EBIT / (Net WC + Net Fixed Assets)**
          投下資本に対してどれだけ利益を生んだか（資本効率）

        - **Earnings Yield = EBIT / Enterprise Value**
          企業価値に対してどれだけ利益が出ているか（割安度）

        - **組み合わせる理由**: 良い会社は普通高い。両方が高い銘柄は
          「割安に放置されている良い会社」= 逆境にあるが本質的に強い会社

        ### Phase 2 推奨根拠カード

        - 上位 5 銘柄について Tavily/Exa で銘柄ニュース・マクロ・地政学・
          研究の 4 系統 + 投資家レンズ（Buffett-Munger 質×価値、Burry
          テールリスク）を取得
        - Claude Haiku で Tetlock 2007 流のセンチメント定量化
        - 「なぜ推すか」の根拠をカード形式でランキング横に併記

        ### リスク

        - **Value Trap**: 構造不況業種は永久に割安なまま
        - **直近 5 年は SP500 にアンダーパフォーム**: 規律保つことが必要
        - **金融・公益・エネルギー除外**: ROC 計算が異質なため
        - **センチメント補助**: ニュース要約は判断補助、最終判断は自分

        ### 学習リソース

        - Greenblatt "The Little Book That Still Beats the Market"
        - Montier 2006 "The Little Book of Behavioral Investing"
        - Tetlock 2007 "Giving Content to Investor Sentiment"
        """
    )
