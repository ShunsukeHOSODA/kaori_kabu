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

Phase 2 推奨根拠カード:
    Tavily/Exa + Claude Haiku キーが揃えば、結果上位 5 銘柄について
    自動でニュース 4 系統 + 投資家レンズ（Buffett-Munger / Burry 既定）+
    センチメント分析を実行し、各銘柄の「なぜ推すか」をカードで併記する。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pandas as pd
import streamlit as st

from src.analysis.composite import (
    CompositeScoreInputs,
    GrowthSubScoreInputs,
    IncomeSubScoreInputs,
    MomentumSubScoreInputs,
    PRESET_DISPLAY_LABELS,
    PRESET_RATIONALE,
    QualitySubScoreInputs,
    RiskSubScoreInputs,
    ValueSubScoreInputs,
    compute_composite_score,
)
from src.analysis.investor_lenses import INVESTOR_LENSES, apply_lenses
from src.analysis.magic_formula import (
    MagicFormulaResult,
    screen_magic_formula_with_provenance,
)
from src.analysis.sentiment import (
    SentimentResult,
    analyze_sentiment,
)
from src.config.settings import settings
from src.data.cache import ParquetCache
from src.data.eodhd import EODHDAPIError, EODHDClient
from src.data.famous_holdings import get_famous_owners, render_owner_badges
from src.data.news import MarketContext, NewsClient
from src.data.yfinance import YFinanceClient, make_default_yfinance_client
from src.strategies.kelly import KellyParams, build_kelly_recommendation
from src.ui.components import (
    composite_radar_chart,
    format_lenses_applied,
    format_sentiment_emoji,
    format_sentiment_label,
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
# データソース層
# ---------------------------------------------------------------------------


@st.cache_data
def load_demo_universe() -> pd.DataFrame:
    """米国大型株 10 銘柄のサンプル財務データ（合成）。

    EODHD API キー未設定時のフォールバック。値は教育用の合成データであり
    実際の財務数値ではない。
    """
    tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "NVDA", "JNJ", "PG", "KO", "WMT",
    ]
    ebit = [
        "120000", "100000", "80000", "60000", "50000",
        "30000", "25000", "20000", "15000", "12000",
    ]
    nwc = [
        "50000", "60000", "70000", "40000", "30000",
        "20000", "30000", "10000", "12000", "8000",
    ]
    nfa = [
        "50000", "70000", "80000", "150000", "30000",
        "15000", "30000", "20000", "25000", "60000",
    ]
    ev = [
        "3500000", "3000000", "1900000", "1800000", "1300000",
        "2500000", "400000", "350000", "260000", "450000",
    ]
    return pd.DataFrame(
        {
            "ticker": tickers,
            "ebit": [Decimal(v) for v in ebit],
            "net_working_capital": [Decimal(v) for v in nwc],
            "net_fixed_assets": [Decimal(v) for v in nfa],
            "enterprise_value": [Decimal(v) for v in ev],
        }
    )


@st.cache_resource
def get_eodhd_client() -> EODHDClient | None:
    """``EODHD_API_KEY`` がある場合のみ EODHDClient を生成。

    EOD 価格（Momentum 用）に使う。Fundamentals は `$59.99 単体 / $99.99
    ALL-IN-ONE` プラン以上が必要なので、本ダッシュボードでは yfinance に
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


def fetch_real_universe(
    client: YFinanceClient,
    tickers: list[str],
    *,
    exchange: str,
    excluded_sectors: tuple[str, ...],
    min_market_cap_usd: Decimal,
) -> pd.DataFrame:
    """yfinance ライブで指定ティッカーのファンダから DataFrame を構築。

    取得は :meth:`YFinanceClient.build_screener_universe` 経由でフィルタ込み。
    EODHDClient.build_screener_universe と同シグネチャ・同 dict shape のため、
    将来 EODHD Fundamentals アップグレード時は注入元を差し替えるだけで済む。
    """
    return client.build_screener_universe(
        tickers,
        exchange=exchange,
        excluded_sectors=excluded_sectors,
        min_market_cap_usd=min_market_cap_usd,
    )


def parse_tickers(raw: str) -> list[str]:
    """カンマまたは改行区切りのティッカー文字列を正規化。

    重複除去 + 大文字化 + 空白除去。
    """
    parts = [
        p.strip().upper()
        for line in raw.splitlines()
        for p in line.split(",")
    ]
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _to_decimal_or_none(value: Any) -> Decimal | None:
    """EODHD ファンダの数値（int/float/None/"None"）→ Decimal | None。"""
    if value is None or value == "None":
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return None


def build_composite_inputs_from_fundamentals(
    fundamentals: dict[str, Any],
    *,
    current_price_jpy: Decimal,
    sentiment_score: Decimal = Decimal("0"),
    sentiment_confidence: Decimal = Decimal("0"),
    momentum_12m: Decimal | None = None,
    momentum_inputs: MomentumSubScoreInputs | None = None,
) -> CompositeScoreInputs | None:
    """EODHD ``/fundamentals/`` の dict から Composite Score 入力を構築。

    欠損フィールドは ``None`` / ``Decimal("0")`` で fallback。連続増配年数 /
    連続赤字年数は履歴解析が必要なため Phase 3.1a では 0 固定（Phase 3.1b で
    精緻化）。Beneish M / Short interest は Phase 3.2 で追加。

    ``momentum_inputs`` は :func:`EODHDClient.get_returns` の結果を呼び出し側で
    包んで渡す（Phase 3.1b で配線）。``None`` のとき Momentum 軸は 0 点。
    ``momentum_12m`` は警告（Falling Knife）判定で使われ、こちらも省略可。
    """
    try:
        general = fundamentals.get("General", {})
        highlights = fundamentals.get("Highlights", {})
        financials = fundamentals.get("Financials", {})
        income_yearly = financials.get("Income_Statement", {}).get("yearly", {})
        balance_yearly = financials.get("Balance_Sheet", {}).get("yearly", {})
        cashflow_yearly = financials.get("Cash_Flow", {}).get("yearly", {})

        if not income_yearly or not balance_yearly:
            return None

        latest_income = income_yearly[max(income_yearly.keys())]
        latest_balance = balance_yearly[max(balance_yearly.keys())]
        latest_cashflow: dict[str, Any] = (
            cashflow_yearly[max(cashflow_yearly.keys())]
            if cashflow_yearly
            else {}
        )

        # 共通: 時価総額 / EV / セクター
        market_cap = _to_decimal_or_none(highlights.get("MarketCapitalization"))
        ev = _to_decimal_or_none(highlights.get("EnterpriseValue"))
        sector = general.get("Sector") or general.get("GicSector")

        # Income inputs
        annual_div = _to_decimal_or_none(highlights.get("ForwardAnnualDividendRate"))
        payout = _to_decimal_or_none(highlights.get("PayoutRatio"))
        # buyback: capital_expenditure と区別、commonStockRepurchased を使う
        buybacks_raw = latest_cashflow.get("commonStockRepurchased")
        buybacks = abs(_to_decimal_or_none(buybacks_raw) or Decimal("0"))
        # FCF = operating cashflow - capex（capex は通常負）
        op_cf = _to_decimal_or_none(
            latest_cashflow.get("totalCashFromOperatingActivities")
        )
        capex = _to_decimal_or_none(latest_cashflow.get("capitalExpenditures"))
        fcf: Decimal | None = None
        if op_cf is not None and capex is not None:
            fcf = op_cf - abs(capex)

        # Risk inputs
        ca = _to_decimal_or_none(latest_balance.get("totalCurrentAssets")) or Decimal("0")
        cl = _to_decimal_or_none(latest_balance.get("totalCurrentLiabilities")) or Decimal("0")
        wc = ca - cl
        re = _to_decimal_or_none(latest_balance.get("retainedEarnings")) or Decimal("0")
        ebit = _to_decimal_or_none(latest_income.get("operatingIncome")) or Decimal("0")
        total_liab = (
            _to_decimal_or_none(latest_balance.get("totalLiab"))
            or _to_decimal_or_none(latest_balance.get("totalLiabilities"))
            or Decimal("1")
        )
        sales = _to_decimal_or_none(latest_income.get("totalRevenue")) or Decimal("0")
        total_assets = (
            _to_decimal_or_none(latest_balance.get("totalAssets")) or Decimal("1")
        )
        net_debt = _to_decimal_or_none(highlights.get("NetDebt")) or Decimal("0")
        ebitda = (
            _to_decimal_or_none(highlights.get("EBITDA"))
            or _to_decimal_or_none(latest_income.get("ebitda"))
            or Decimal("0")
        )

        # Quality inputs
        roe = _to_decimal_or_none(highlights.get("ReturnOnEquityTTM"))
        roa = _to_decimal_or_none(highlights.get("ReturnOnAssetsTTM"))
        gross_profit = _to_decimal_or_none(latest_income.get("grossProfit"))
        gross_margin: Decimal | None = (
            (gross_profit / sales) if (gross_profit is not None and sales > 0) else None
        )

        return CompositeScoreInputs(
            income=IncomeSubScoreInputs(
                forward_dividend_per_share_jpy=annual_div,
                current_price_jpy=current_price_jpy,
                payout_ratio=payout,
                consecutive_dividend_years=0,  # Phase 3.1b で履歴解析
                buybacks_4q_jpy=buybacks,
                market_cap_jpy=market_cap or Decimal("1"),
                free_cash_flow_jpy=fcf,
                enterprise_value_jpy=ev,
                sector=sector,
            ),
            risk=RiskSubScoreInputs(
                working_capital_jpy=wc,
                retained_earnings_jpy=re,
                ebit_jpy=ebit,
                market_cap_jpy=market_cap or Decimal("1"),
                total_liabilities_jpy=total_liab,
                sales_jpy=sales,
                total_assets_jpy=total_assets,
                net_debt_jpy=net_debt,
                ebitda_jpy=ebitda,
                short_interest_pct=None,
                consecutive_loss_years=0,  # Phase 3.1b
                beneish_m_score=None,
            ),
            quality=QualitySubScoreInputs(
                roe=roe, roa=roa, gross_margin=gross_margin
            ),
            sentiment_score=sentiment_score,
            sentiment_confidence=sentiment_confidence,
            momentum_12m_return=momentum_12m,
            value=ValueSubScoreInputs(
                ebit_jpy=ebit if ebit > 0 else None,
                enterprise_value_jpy=ev,
            ),
            growth=_build_growth_inputs(highlights, income_yearly),
            momentum=momentum_inputs,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_momentum_inputs(
    client: EODHDClient,
    ticker: str,
    *,
    exchange: str,
) -> MomentumSubScoreInputs | None:
    """EODHD ``get_returns`` を呼んで :class:`MomentumSubScoreInputs` を構築。

    24h キャッシュ（``data/cache/EODHD/eod_*.parquet``）を共有するので
    同セッションで複数回呼んでも API 消費は 1 銘柄 1 回。

    取得失敗・履歴 0 件などは ``None`` を返し、Composite 集約器側で
    Momentum 軸を 0 点にフォールバックする。Streamlit ページで例外を
    上げない（ループ全体を停止させないための境界処理）。
    """
    try:
        returns = client.get_returns(ticker, exchange=exchange)
    except (httpx.HTTPError, EODHDAPIError, ValueError, KeyError):
        return None
    if returns["return_12m"] is None and returns["return_1m"] is None:
        return None
    return MomentumSubScoreInputs(
        return_12m=returns["return_12m"],
        return_1m=returns["return_1m"],
    )


def _build_growth_inputs(
    highlights: dict[str, Any],
    income_yearly: dict[str, Any],
) -> GrowthSubScoreInputs | None:
    """EODHD highlights + income yearly から Growth 入力を構築。

    5y CAGR は yearly データから計算、不足時は None。
    PEG は PER × 期待成長率（forward 推奨）から内部計算。
    """
    if not highlights:
        return None

    pe_ratio = _to_decimal_or_none(highlights.get("PERatio"))
    earnings_growth_rate = _to_decimal_or_none(
        highlights.get("QuarterlyEarningsGrowthYOY")
    )
    dividend_growth = _to_decimal_or_none(
        highlights.get("DividendGrowth5Years")
    )
    revenue_cagr = _compute_cagr_from_yearly(income_yearly, "totalRevenue", years=5)
    eps_cagr = _compute_cagr_from_yearly(income_yearly, "dilutedEps", years=5)

    return GrowthSubScoreInputs(
        revenue_5y_cagr=revenue_cagr,
        eps_5y_cagr=eps_cagr,
        dividend_5y_cagr=dividend_growth,
        pe_ratio=pe_ratio,
        earnings_growth_rate=earnings_growth_rate,
    )


def _compute_cagr_from_yearly(
    yearly: dict[str, Any],
    field: str,
    *,
    years: int = 5,
) -> Decimal | None:
    """yearly dict (date 文字列キー) から N 年 CAGR を計算。

    成長率 = (latest / past) ** (1/N) - 1。past または latest が 0 / 負 / 欠損なら None。
    """
    if not yearly:
        return None
    sorted_keys = sorted(yearly.keys())
    if len(sorted_keys) < years + 1:
        return None
    latest = _to_decimal_or_none(yearly[sorted_keys[-1]].get(field))
    past = _to_decimal_or_none(yearly[sorted_keys[-(years + 1)]].get(field))
    if latest is None or past is None or past <= 0 or latest <= 0:
        return None
    # CAGR = (latest/past)^(1/years) - 1
    ratio = float(latest) / float(past)
    cagr = ratio ** (1.0 / years) - 1.0
    return Decimal(str(round(cagr, 6)))


# ---------------------------------------------------------------------------
# 推奨根拠分析（Phase 2）
# ---------------------------------------------------------------------------


def analyze_recommendation_for_ticker(
    ticker: str,
    *,
    news_client: NewsClient,
    anthropic_client: Any,
    lenses: tuple[str, ...],
) -> tuple[MarketContext, SentimentResult, pd.DataFrame] | None:
    """単一銘柄について 4 系統 + レンズ + センチメント分析を実行。

    例外時は ``None`` を返してカードを「分析失敗」表示にする。
    """
    try:
        market_context = news_client.gather_market_context(ticker)
        lens_df = (
            apply_lenses(news_client, ticker=ticker, lenses=lenses)
            if lenses
            else pd.DataFrame()
        )
        combined = pd.concat(
            [
                market_context.ticker_news,
                market_context.macro_news,
                market_context.geopolitical_news,
                market_context.research,
                lens_df,
            ],
            ignore_index=True,
            sort=False,
        )
        sentiment = analyze_sentiment(
            combined, ticker=ticker, anthropic_client=anthropic_client
        )
    except Exception:  # noqa: BLE001 — UI 側で安全に失敗表示
        return None
    return market_context, sentiment, combined


def render_recommendation_card(
    *,
    rank: int,
    ticker: str,
    magic_formula_row: dict[str, Any],
    market_context: MarketContext | None,
    sentiment: SentimentResult,
    lenses_applied: tuple[str, ...],
) -> None:
    """推奨根拠カード 1 枚を描画（結果テーブル直下に並ぶ）。"""
    score = sentiment.sentiment_score
    emoji = format_sentiment_emoji(score)
    label = format_sentiment_label(score)

    rank_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    rank_label = rank_emoji[rank - 1] if rank <= len(rank_emoji) else f"#{rank}"

    with st.container(border=True):
        # ヘッダー: ランク + ティッカー + Magic Formula スコア + センチメント
        header_cols = st.columns([1, 4, 3])
        with header_cols[0]:
            st.markdown(f"### {rank_label}")
        with header_cols[1]:
            st.markdown(f"### **{ticker}**")
            mf = magic_formula_row
            st.caption(
                f"Magic Formula スコア `{mf.get('magic_formula_score', '—')}` ／ "
                f"ROC `{mf.get('roc', '—')}` ／ EY `{mf.get('earnings_yield', '—')}`"
                + (
                    f"\nセクター: {mf.get('sector')}"
                    if mf.get("sector")
                    else ""
                )
            )
        with header_cols[2]:
            st.markdown(f"### {emoji} {label}")
            st.caption(
                f"score `{score}` / conf `{sentiment.confidence}`"
            )

        # 要約（推奨根拠の中心）
        if sentiment.summary:
            st.markdown(f"💡 **推奨根拠**: {sentiment.summary}")

        # 主要テーマ + リスクシグナル
        cols = st.columns(2)
        with cols[0]:
            if sentiment.key_themes:
                st.markdown("**主要テーマ**")
                for theme in sentiment.key_themes:
                    st.markdown(f"- {theme}")
            else:
                st.caption("主要テーマ: —")
        with cols[1]:
            if sentiment.risk_signals:
                st.markdown("⚠️ **リスクシグナル**")
                for signal in sentiment.risk_signals:
                    st.markdown(f"- {signal}")
            else:
                st.caption("リスクシグナル: —")

        # 適用レンズ + ソース URL
        if lenses_applied:
            st.caption(f"適用レンズ: {format_lenses_applied(lenses_applied)}")

        if market_context is not None:
            all_news = pd.concat(
                [
                    market_context.ticker_news,
                    market_context.macro_news,
                    market_context.geopolitical_news,
                    market_context.research,
                ],
                ignore_index=True,
                sort=False,
            )
            if len(all_news) > 0 and "url" in all_news.columns:
                with st.expander(f"🔗 ソース URL ({len(all_news)} 件、上位 5 表示)"):
                    for _, row in all_news.head(5).iterrows():
                        title = str(row.get("title", "")).strip()
                        url = str(row.get("url", "")).strip()
                        if url and url != "nan":
                            st.markdown(f"- [{title or url}]({url})")

        # Provenance（CLAUDE.md §9.8.5 必須）
        with st.expander("ⓘ 出所追跡情報"):
            md = sentiment.metadata
            st.json(
                {
                    "model_version": md.model_version,
                    "calculation_method": md.calculation_method,
                    "input_news_count": md.input_news_count,
                    "academic_source": md.academic_source,
                    "calculated_at": md.calculated_at.isoformat(),
                    "code_commit": md.code_commit,
                    "lenses_applied": list(lenses_applied),
                }
            )


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

# 推奨根拠カードに自動分析する銘柄数（待ち時間を許容、視界に収まる粒度のベスト）
TOP_PICKS_FOR_NEWS: int = 5
DEFAULT_NEWS_LENSES: tuple[str, ...] = ("Buffett_Munger", "Burry")

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

    if real_mode:
        _default = (
            _DEFAULT_TICKERS_JP if exchange == "TO" else _DEFAULT_TICKERS_US
        )
        if exchange == "TO":
            st.caption(
                "🇯🇵 東証選択中: 4 桁証券コードで入力（例: 7203 = トヨタ）。"
                "yfinance が `.T` 付きで取得します。"
            )
        ticker_text = st.text_area(
            "ティッカー（カンマまたは改行区切り）",
            value=_default,
            height=120,
            key=f"ticker_input_{exchange}",  # 取引所切替時の再描画
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
# 実行
# ---------------------------------------------------------------------------


if run_button:
    if real_mode and eodhd_client is not None:
        with st.spinner(
            f"yfinance から {len(tickers)} 銘柄のファンダ取得中..."
        ):
            try:
                df = fetch_real_universe(
                    yfinance_client,
                    tickers,
                    exchange=exchange,
                    excluded_sectors=tuple(excluded),
                    min_market_cap_usd=Decimal(str(min_market_cap)),
                )
            except Exception as exc:  # noqa: BLE001 — UI 側で安全に表示
                st.error(f"❌ 取得失敗: {exc}")
                st.stop()
        if df.empty:
            st.warning(
                "⚠️ フィルタ後に該当銘柄が 0 件。"
                "セクター除外・最低時価総額・ティッカー指定を見直してください。"
            )
            st.stop()
        data_source = f"yfinance fundamentals + EODHD prices ({exchange})"
        data_period = pd.Timestamp.now(tz="UTC").strftime(
            "fundamentals_as_of_%Y-%m-%d"
        )
        cache_hit_flag: bool | None = None
    else:
        df = load_demo_universe()
        data_source = "demo_fixture_10_us_large_cap"
        data_period = "N/A (synthetic)"
        cache_hit_flag = False

    with st.spinner("Magic Formula 計算中..."):
        result: MagicFormulaResult = screen_magic_formula_with_provenance(
            df,
            n=top_n,
            input_data_source=data_source,
            input_data_period=data_period,
            input_cache_hit=cache_hit_flag,
        )

    st.success(
        f"✅ Top {len(result.result)} 銘柄を抽出 "
        f"({result.metadata.calculated_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
    )

    # ───────────────────────────────────────────────
    # Provenance 開示（CLAUDE.md §9.8.5）
    # ───────────────────────────────────────────────
    with st.expander("ⓘ 出所追跡情報（Provenance）"):
        st.json(
            {
                "calculation_method": result.metadata.calculation_method,
                "academic_source": result.metadata.academic_source,
                "calculated_at": result.metadata.calculated_at.isoformat(),
                "input_data_source": result.metadata.input_data_source,
                "input_data_period": result.metadata.input_data_period,
                "input_cache_hit": result.metadata.input_cache_hit,
                "code_commit": result.metadata.code_commit,
            }
        )

    # ───────────────────────────────────────────────
    # 結果テーブル
    # ───────────────────────────────────────────────
    display_columns = [
        "ticker",
        "magic_formula_score",
        "roc",
        "earnings_yield",
        "roc_rank",
        "ey_rank",
    ]
    if "sector" in result.result.columns:
        display_columns.append("sector")
    if "market_cap" in result.result.columns:
        display_columns.append("market_cap")

    display_df = result.result[display_columns].copy()
    display_df["roc"] = display_df["roc"].apply(
        lambda x: f"{float(x) * 100:.2f}%"
    )
    display_df["earnings_yield"] = display_df["earnings_yield"].apply(
        lambda x: f"{float(x) * 100:.2f}%"
    )
    if "market_cap" in display_df.columns:
        display_df["market_cap"] = display_df["market_cap"].apply(
            lambda x: f"${float(x) / 1e9:,.1f}B" if x is not None else "—"
        )

    rename_map = {
        "ticker": "ティッカー",
        "magic_formula_score": "合算スコア（小さいほど良い）",
        "roc": "資本利益率(ROC)",
        "earnings_yield": "益利回り(EY)",
        "roc_rank": "ROC 順位",
        "ey_rank": "EY 順位",
        "sector": "セクター",
        "market_cap": "時価総額",
    }
    display_df = display_df.rename(columns=rename_map)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ───────────────────────────────────────────────
    # 推奨根拠カード（Phase 2: ニュース・センチメント・レンズ統合）
    # ───────────────────────────────────────────────
    if (
        enable_news_cards
        and news_client is not None
        and anthropic_client is not None
    ):
        st.subheader(f"📋 上位 {TOP_PICKS_FOR_NEWS} 銘柄の推奨根拠")
        st.caption(
            f"Tavily/Exa で 4 系統ニュース取得 + 投資家レンズ "
            f"({format_lenses_applied(DEFAULT_NEWS_LENSES)}) + Claude Haiku "
            "でセンチメント分析。「なぜ推すか」の根拠をカードで併記。"
        )

        top_picks = result.result.head(TOP_PICKS_FOR_NEWS)
        progress = st.progress(0, text="推奨根拠を分析中...")

        analyses: list[tuple[int, str, dict[str, Any], Any]] = []
        for idx, (_, mf_row) in enumerate(top_picks.iterrows()):
            ticker_name = str(mf_row["ticker"])
            progress.progress(
                (idx + 1) / len(top_picks),
                text=f"分析中: {ticker_name} ({idx + 1}/{len(top_picks)})",
            )
            analysis = analyze_recommendation_for_ticker(
                ticker_name,
                news_client=news_client,
                anthropic_client=anthropic_client,
                lenses=DEFAULT_NEWS_LENSES,
            )
            analyses.append((idx + 1, ticker_name, mf_row.to_dict(), analysis))

        progress.empty()

        for rank, ticker_name, mf_dict, analysis in analyses:
            if analysis is None:
                with st.container(border=True):
                    st.markdown(f"### {rank}️⃣ **{ticker_name}**")
                    st.warning(
                        "⚠️ ニュース・センチメント分析に失敗。"
                        "API キー / レート制限 / ネットワークを確認してください。"
                    )
                continue
            mc, sent, _ = analysis
            # market_cap などの Decimal を表示用に整形
            mf_display = {
                "magic_formula_score": mf_dict.get("magic_formula_score", "—"),
                "roc": (
                    f"{float(mf_dict['roc']) * 100:.2f}%"
                    if "roc" in mf_dict
                    else "—"
                ),
                "earnings_yield": (
                    f"{float(mf_dict['earnings_yield']) * 100:.2f}%"
                    if "earnings_yield" in mf_dict
                    else "—"
                ),
                "sector": mf_dict.get("sector", ""),
            }
            render_recommendation_card(
                rank=rank,
                ticker=ticker_name,
                magic_formula_row=mf_display,
                market_context=mc,
                sentiment=sent,
                lenses_applied=DEFAULT_NEWS_LENSES,
            )

    # ───────────────────────────────────────────────
    # 📋 Composite Score 詳細（Phase 3.1a — 世界一投資家網羅）
    # ───────────────────────────────────────────────
    if enable_composite and real_mode and eodhd_client is not None:
        st.subheader("📋 Composite Score 詳細（投資家視点の総合スコア）")
        st.caption(
            f"投資スタイル: **{PRESET_DISPLAY_LABELS[composite_preset]}** — "
            f"{PRESET_RATIONALE[composite_preset]}"
        )
        # §4.2 #3: Half-Kelly 推奨サイズの注記（暫定値の根拠を明示、§9.4 / §9.7）
        st.info(
            "📌 **Half-Kelly 推奨** は暫定値で計算: "
            "**勝率 60%**（Magic Formula 経験則、Greenblatt 2010）/ "
            "**損益比 2.0**（ATR 2R ストップ設計）/ "
            "**1 銘柄上限 5%**（Overconfidence 対策、Thorp 2006）。"
            "実バックテスト結果が揃い次第、銘柄別の実測値で更新予定。"
        )

        # Half-Kelly 暫定パラメータ（保守的、後で実バックテストで上書き）
        _kelly_params_default = KellyParams(
            win_rate=Decimal("0.6"),
            win_loss_ratio=Decimal("2.0"),
        )
        _portfolio_value_jpy_dec = Decimal(str(portfolio_value_jpy_input))

        composite_rows: list[dict[str, Any]] = []
        composite_warnings: list[tuple[str, list[Any]]] = []
        radar_data: list[tuple[str, float, dict[str, float]]] = []
        progress = st.progress(0, text="Composite Score 計算中...")

        for idx, (_, mf_row) in enumerate(result.result.iterrows()):
            ticker_name = str(mf_row["ticker"])
            ticker_exchange = str(mf_row.get("exchange", exchange))
            progress.progress(
                (idx + 1) / len(result.result),
                text=f"Composite 計算中: {ticker_name} ({idx + 1}/{len(result.result)})",
            )
            try:
                fundamentals = yfinance_client.get_fundamentals(
                    ticker_name, exchange=ticker_exchange
                )
            except Exception:  # noqa: BLE001
                continue

            # 現在価格は EOD 取得が高コストなので、ファンダの 52w 価格を代用
            current_price = (
                _to_decimal_or_none(
                    fundamentals.get("Highlights", {}).get("MarketCapitalization")
                )
                or Decimal("1")
            ) / max(
                _to_decimal_or_none(
                    fundamentals.get("SharesStats", {}).get("SharesOutstanding")
                )
                or Decimal("1"),
                Decimal("1"),
            )

            momentum_inputs = _fetch_momentum_inputs(
                eodhd_client, ticker_name, exchange=ticker_exchange
            )
            inputs = build_composite_inputs_from_fundamentals(
                fundamentals,
                current_price_jpy=current_price,
                momentum_inputs=momentum_inputs,
                momentum_12m=(
                    momentum_inputs.return_12m
                    if momentum_inputs is not None
                    else None
                ),
            )
            if inputs is None:
                continue

            composite = compute_composite_score(inputs, preset_name=composite_preset)
            warning_severity = (
                "🚨" if any(w.severity == "RED" for w in composite.warnings)
                else ("⚠️" if composite.warnings else "✅")
            )
            # 達人保有バッジ（要件 §3 反対意見 2: 13F 完全裏化を避け心理的安心材料として併記）
            _owners = get_famous_owners(ticker_name, ticker_exchange)
            _ticker_with_badge = (
                f"{ticker_name} {render_owner_badges(_owners)}" if _owners else ticker_name
            )
            # Half-Kelly 推奨サイズ（暫定値、§4.2 #3）
            _kelly_rec = build_kelly_recommendation(
                params=_kelly_params_default,
                portfolio_value_jpy=_portfolio_value_jpy_dec,
            )
            _kelly_size_jpy = int(Decimal(_kelly_rec["recommended_size_jpy"]))

            composite_rows.append(
                {
                    "ティッカー": _ticker_with_badge,
                    "Composite": f"{composite.composite_score:.1f}",
                    "Q": f"{composite.sub_scores['Q']:.0f}",
                    "V": f"{composite.sub_scores['V']:.0f}",
                    "I": f"{composite.sub_scores['I']:.0f}",
                    "G": f"{composite.sub_scores['G']:.0f}",
                    "R": f"{composite.sub_scores['R']:.0f}",
                    "M": f"{composite.sub_scores['M']:.0f}",
                    "S": f"{composite.sub_scores['S']:.0f}",
                    "Kelly推奨JPY": f"¥{_kelly_size_jpy:,}",
                    "警告": warning_severity,
                }
            )
            if composite.warnings:
                composite_warnings.append(
                    (ticker_name, list(composite.warnings))
                )
            radar_data.append(
                (ticker_name, composite.composite_score, dict(composite.sub_scores))
            )

        progress.empty()

        if composite_rows:
            st.dataframe(
                pd.DataFrame(composite_rows).sort_values(
                    "Composite", ascending=False
                ),
                use_container_width=True,
                hide_index=True,
            )
            if composite_warnings:
                with st.expander(
                    f"⚠️ 警告詳細（{len(composite_warnings)} 銘柄）"
                ):
                    for tk, warns in composite_warnings:
                        st.markdown(f"**{tk}**")
                        for w in warns:
                            icon = (
                                "🚨" if w.severity == "RED"
                                else ("⚠️" if w.severity == "AMBER" else "ℹ️")
                            )
                            st.markdown(f"- {icon} `{w.code}`: {w.message}")
            st.caption(
                "Q=Quality / V=Value / I=Income / G=Growth / R=Risk / "
                "M=Momentum / S=Sentiment（各 0-100）。"
                "Composite はプリセット重み付け合算（0-100）。"
                "詳細設計: `docs/long-term-investment-architecture.md`"
            )

            # 7 軸レーダーチャート — 上位 N 銘柄を並べて視覚比較
            top_n = sorted(
                radar_data, key=lambda r: r[1], reverse=True
            )[:3]
            if top_n:
                st.markdown("##### 🎯 上位銘柄 7 軸レーダーチャート")
                cols = st.columns(len(top_n))
                for col, (tk, score, subs) in zip(cols, top_n, strict=False):
                    with col:
                        fig = composite_radar_chart(ticker=tk, sub_scores=subs)
                        st.plotly_chart(
                            fig,
                            use_container_width=True,
                            key=f"radar_{tk}",
                        )
                        st.caption(f"Composite: **{score:.1f}** / 100")
        else:
            st.info(
                "Composite Score を計算できる銘柄がありませんでした"
                "（ファンダ取得失敗 or 必須フィールド欠損）"
            )

    # ───────────────────────────────────────────────
    # リスク警告（CLAUDE.md §9.4 / §9.7）
    # ───────────────────────────────────────────────
    risk_messages = [
        "**過去パフォーマンス ≠ 将来**: 直近 5 年は SP500 にアンダーパフォーム",
        "**Value Trap リスク**: 構造不況業種は永久に割安なまま",
        "**認知バイアス対策**: Confirmation Bias を避け、反対意見も検討すること",
    ]
    if not real_mode:
        risk_messages.insert(0, "**デモデータ**: このページは合成 10 銘柄のサンプルです")
    if enable_news_cards:
        risk_messages.append(
            "**センチメントは補助情報**: ニュース要約は判断の補助、最終判断は自分で"
        )
    if enable_composite and real_mode:
        risk_messages.append(
            "**総合スコアは Phase 3.1b 時点の暫定値**: ROIC/WACC・連続増配年数・"
            "13F 機関投資家保有・株主優待は Phase 3.2 以降で精緻化予定"
        )
    st.warning("⚠️ **リスク警告**\n\n- " + "\n- ".join(risk_messages))

else:
    st.info("左サイドバーでパラメータを設定し「スクリーニング実行」を押してください。")


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
