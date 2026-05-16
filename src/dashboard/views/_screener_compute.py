"""Magic Formula スクリーナー計算パイプライン（Phase 5.5.0 で 02_screener.py から切り出し）。

handoff-session-6 §5.1 / Phase 5.4.4 C-H-2 指摘の解消:
    02_screener.py の ``if run_button:`` 配下 407 行 (L1247-1654 旧) を
    :func:`run_screening_pipeline` 1 つに集約する。

責務分離:
    - ``_screener_display.py``: 計算済みデータの描画専用
    - 本モジュール: run_button 経路の計算ロジック（データ取得 + Magic Formula +
      推奨カード分析 + Composite ループ + Sonnet ranking judge + session 構築）
    - ``02_screener.py``: ページエントリ + サイドバー UI + 制御フロー + BUY フォーム

入出力規約:
    入力: サイドバー UI で確定した user パラメータ + Streamlit @cache_resource
        経由で取得した 4 種 client（``eodhd_client`` / ``yfinance_client`` /
        ``news_client`` / ``anthropic_client``）。
    出力: 計算済み :class:`ScreeningSession` 1 個。
    副作用: ``st.spinner`` / ``st.progress`` / ``st.error`` / ``st.warning`` の
        Streamlit UI フィードバック呼び出しのみ。失敗時は ``st.stop()`` で停止。

PRD §FR5 多段縮退規約 (Phase 5.4.2 で実装、本 Phase 5.5.0 で挙動保全):
    Polymarket / 13F / Regime / Sonnet 個別失敗時は空 dict + ``st.warning`` で
    続行し、Composite ランキングのみで動作継続。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

from src.analysis._adapters import magic_formula_result_to_per_ticker_dict
from src.analysis._anthropic_types import AnthropicLike
from src.analysis._sonnet_model_resolver import resolve_sonnet_model_version
from src.analysis.composite import (
    CompositeScoreInputs,
    GrowthSubScoreInputs,
    IncomeSubScoreInputs,
    MomentumSubScoreInputs,
    QualitySubScoreInputs,
    RiskSubScoreInputs,
    ValueSubScoreInputs,
    compute_composite_score,
)
from src.analysis.composite.aggregator import CompositeScoreResult
from src.analysis.investor_lenses import apply_lenses
from src.analysis.magic_formula import (
    MagicFormulaResult,
    screen_magic_formula_with_provenance,
)
from src.analysis.ranking_judge import (
    FALLBACK_REASON_LABELS,
    RankingResult,
    RankingSignalBundle,
    classify_api_exception,
    rank_with_claude_batch,
)
from src.analysis.sentiment import (
    SentimentResult,
    analyze_sentiment,
)
from src.analysis.signal_aggregator import aggregate_signals_for_universe
from src.config.settings import settings
from src.dashboard.views._screener_session import (
    DEFAULT_NEWS_LENSES,
    TOP_PICKS_FOR_NEWS,
    RecommendationAnalysis,
    ScreeningSession,
)
from src.data.cache import ParquetCache
from src.data.eodhd import EODHDAPIError, EODHDClient
from src.data.famous_holdings import get_famous_owners, render_owner_badges
from src.data.news import MarketContext, NewsClient
from src.data.yfinance import YFinanceClient
from src.strategies.kelly import KellyParams, build_kelly_recommendation

# ---------------------------------------------------------------------------
# ティッカー入力 / ユニバース取得
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _resolved_sonnet_model_version() -> str:
    """Phase 5.5.3: Sonnet ``model_version`` を起動時に動的解決し session 全体で共有。

    handoff-session-6 §5.7 / C-L-1 の持ち越し課題解消。

    挙動:
        - ``ANTHROPIC_API_KEY`` 未設定 → ``settings.sonnet_model_version`` をそのまま返す。
        - 設定値が prefix のみ (``claude-sonnet-4-6``) → ``anthropic.models.list()`` で
          ``claude-sonnet-4-6-YYYYMMDD`` 形式の最新スナップショットを取得。
        - 設定値が日付付き完全 ID (``claude-sonnet-4-6-20250514``) → prefix としては
          いずれにもマッチしないため fallback (= 同じ値) が返り override が保持される。
        - API 失敗 → fallback (= settings 値) を返す (PRD §FR5 多段縮退)。

    キャッシュライフタイム:
        ``@st.cache_resource`` は Streamlit プロセスライフタイムで cache される。
        **アプリ再起動で更新される**ため、Anthropic が新スナップショットを追加しても
        プロセスが生存中は古い解決結果のまま固定される。長時間稼働時は
        ``.env`` の ``SONNET_MODEL_VERSION`` を明示 override で固定する運用が確実
        (Phase 5.5.6 P-LOW-1 / C-MEDIUM-2 一致指摘)。
    """
    if not settings.anthropic_api_key:
        return settings.sonnet_model_version
    import anthropic  # noqa: PLC0415 — オプショナル機能の lazy import

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except Exception:  # noqa: BLE001 — 初期化失敗時は settings 値で続行
        return settings.sonnet_model_version
    return resolve_sonnet_model_version(
        client,
        prefix=settings.sonnet_model_version,
        fallback=settings.sonnet_model_version,
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


# ---------------------------------------------------------------------------
# Composite Score / Growth / Momentum 入力構築
# ---------------------------------------------------------------------------


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

    CLAUDE.md §9.1 に従い float を経由せず Decimal の ``ln`` / ``exp`` で計算する。
    ``exp(ln(ratio) / years) - 1`` は数学的に ``ratio ** (1/years) - 1`` と等価。
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
    ratio = latest / past
    cagr = (ratio.ln() / Decimal(years)).exp() - Decimal(1)
    return cagr.quantize(Decimal("0.000001"))


# ---------------------------------------------------------------------------
# 推奨根拠分析（Phase 2、Tavily/Exa + 投資家レンズ + Claude Haiku）
# ---------------------------------------------------------------------------


def analyze_recommendation_for_ticker(
    ticker: str,
    *,
    news_client: NewsClient,
    anthropic_client: AnthropicLike,
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
    except Exception as exc:  # noqa: BLE001 — UI 側で安全に失敗表示
        # Phase 5.5.6 C-LOW-2: observability のため logger.warning を追加
        # (UI 側ではカードに「分析失敗」表示、debug 時は log で原因追跡)
        logger.warning(
            "analyze_recommendation_for_ticker failed for %s: %s: %s",
            ticker,
            type(exc).__name__,
            exc,
        )
        return None
    return market_context, sentiment, combined


# ---------------------------------------------------------------------------
# パイプライン entry: run_button 経路の全計算
# ---------------------------------------------------------------------------


def run_screening_pipeline(
    *,
    tickers: list[str],
    real_mode: bool,
    exchange: str,
    excluded: list[str],
    min_market_cap: int,
    top_n: int,
    enable_news_cards: bool,
    enable_composite: bool,
    composite_preset: str,
    portfolio_value_jpy_input: int,
    eodhd_client: EODHDClient | None,
    yfinance_client: YFinanceClient,
    news_client: NewsClient | None,
    anthropic_client: AnthropicLike | None,
) -> ScreeningSession:
    """run_button 経路の計算パイプライン全体。

    既存挙動を完全保全し (Phase 5.4.4 commit a863a0b の出力と bit-equal)、
    サイドバー UI で確定したパラメータと Streamlit ``@cache_resource`` 経由の
    client を受け取って :class:`ScreeningSession` を返す。

    失敗時の挙動 (元コードと同じ):
        - データ取得失敗: ``st.error`` + ``st.stop()``
        - フィルタ後 0 件: ``st.warning`` + ``st.stop()``
        - Polymarket / 13F / Regime / Sonnet 個別失敗: ``st.warning`` で警告、
          続行（PRD §FR5 多段縮退、Phase 5.4.2 で実装）

    Returns:
        :class:`ScreeningSession`: 計算結果 + 制御フラグ + BUY フォーム用追加状態。
    """
    # ── 1. データ取得 ────────────────────────────────────────────
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

    # ── 2. Magic Formula 計算 ────────────────────────────────────
    with st.spinner("Magic Formula 計算中..."):
        result: MagicFormulaResult = screen_magic_formula_with_provenance(
            df,
            n=top_n,
            input_data_source=data_source,
            input_data_period=data_period,
            input_cache_hit=cache_hit_flag,
        )

    # ── 3. 推奨根拠カード分析 (Phase 2) ──────────────────────────
    analyses: list[RecommendationAnalysis] | None = None
    if (
        enable_news_cards
        and news_client is not None
        and anthropic_client is not None
    ):
        top_picks = result.result.head(TOP_PICKS_FOR_NEWS)
        progress = st.progress(0, text="推奨根拠を分析中...")
        analyses = []
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

    # Phase 5.4.2: 推奨根拠カードの sentiment を ticker 別 dict に詰め直す
    # (Sonnet シグナル束の sentiment_results に渡す用)。
    sentiment_results_dict: dict[str, SentimentResult] = {}
    if analyses is not None:
        for _rank, _ticker_name, _mf_dict, _analysis in analyses:
            if _analysis is not None:
                _mc, _sent, _df = _analysis
                sentiment_results_dict[_ticker_name] = _sent

    # ── 4. Composite Score ループ (Phase 3.1a) ───────────────────
    composite_rows: list[dict[str, Any]] = []
    composite_warnings: list[tuple[str, list[Any]]] = []
    radar_data: list[tuple[str, float, dict[str, float]]] = []
    # Phase 5.4.2: Sonnet 連携用 dict (Composite ループ内で並行構築)
    composite_results_dict: dict[str, CompositeScoreResult] = {}
    momentum_results_dict: dict[str, dict[str, Decimal]] = {}
    # Half-Kelly 暫定パラメータ（保守的、後で実バックテストで上書き）
    kelly_params_default = KellyParams(
        win_rate=Decimal("0.6"),
        win_loss_ratio=Decimal("2.0"),
    )
    portfolio_value_jpy_dec = Decimal(str(portfolio_value_jpy_input))

    if enable_composite and real_mode and eodhd_client is not None:
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
            except Exception as exc:  # noqa: BLE001 — UI フォールバック
                st.warning(
                    f"⚠️ {ticker_name} ファンダ取得失敗 "
                    f"({type(exc).__name__})、スキップ"
                )
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
            # Phase 5.4.2: Sonnet 連携用に composite / momentum を ticker 別 dict に保存
            composite_results_dict[ticker_name] = composite
            if momentum_inputs is not None:
                momentum_results_dict[ticker_name] = {
                    "1m": (
                        momentum_inputs.return_1m
                        if momentum_inputs.return_1m is not None
                        else Decimal("0")
                    ),
                    "12m": (
                        momentum_inputs.return_12m
                        if momentum_inputs.return_12m is not None
                        else Decimal("0")
                    ),
                }
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
                params=kelly_params_default,
                portfolio_value_jpy=portfolio_value_jpy_dec,
            )
            _kelly_size_jpy = int(Decimal(_kelly_rec["recommended_size_jpy"]))

            composite_rows.append(
                {
                    "ティッカー": _ticker_with_badge,
                    "_ticker_raw": ticker_name,  # BUY フォーム用、表示時は drop
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

    # ── 5. Stage 2 Sonnet 連携 + Stage 3 規律強制 (Phase 5.4.2) ──
    ranking_results, signal_bundles = _run_sonnet_stage(
        result=result,
        composite_rows=composite_rows,
        composite_results_dict=composite_results_dict,
        sentiment_results_dict=sentiment_results_dict,
        momentum_results_dict=momentum_results_dict,
        exchange=exchange,
        anthropic_client=anthropic_client,
    )

    # ── 6. ScreeningSession を構築 ───────────────────────────────
    return ScreeningSession(
        result=result,
        composite_rows=composite_rows,
        composite_warnings=composite_warnings,
        radar_data=radar_data,
        analyses=analyses,
        ranking_results=ranking_results,
        signal_bundles=signal_bundles,
        composite_preset=composite_preset,
        real_mode=real_mode,
        enable_news_cards=enable_news_cards,
        enable_composite=enable_composite,
        exchange=exchange,
        kelly_params_default=kelly_params_default,
        portfolio_value_jpy_dec=portfolio_value_jpy_dec,
        calculated_at_iso=result.metadata.calculated_at.isoformat(),
        code_commit=result.metadata.code_commit,
    )


# ---------------------------------------------------------------------------
# Sonnet 連携 (Phase 5.4.2 抽出) — Polymarket + 13F + Regime + Sonnet
# ---------------------------------------------------------------------------


def _run_sonnet_stage(
    *,
    result: MagicFormulaResult,
    composite_rows: list[dict[str, Any]],
    composite_results_dict: dict[str, CompositeScoreResult],
    sentiment_results_dict: dict[str, SentimentResult],
    momentum_results_dict: dict[str, dict[str, Decimal]],
    exchange: str,
    anthropic_client: AnthropicLike | None,
) -> tuple[list[RankingResult] | None, list[RankingSignalBundle] | None]:
    """Stage 2 Sonnet 連携の独立関数。

    Composite ループ後、session 構築前に呼ばれる。6 skill 統合
    → Sonnet ranking judge → Stage 3 純粋関数 (確信度調整 + Kelly 乗数)。
    Anthropic key 不在 / Composite ゼロ件 / 各 step 失敗時は ``(None, None)``
    で縮退し UI は Composite ランキングのみで動作継続 (PRD §FR5)。
    """
    if not settings.anthropic_api_key or not composite_rows:
        if not settings.anthropic_api_key:
            st.info(
                "ℹ️ ANTHROPIC_API_KEY 未設定のため Claude 判定はスキップ"
                "（数式ランキングのみ表示）。"
            )
        return None, None

    with st.spinner("🤖 Claude による総合判定を実行中..."):
        # ----- Step 1: Polymarket マクロ確率取得 (失敗時 空 dict) -----
        try:
            from src.data.polymarket_client import (  # noqa: PLC0415
                fetch_macro_probabilities,
            )

            polymarket_macro_raw = fetch_macro_probabilities(
                topics=[
                    "fed_rate_cut_2026",
                    "us_recession_2026",
                    "geopolitical_risk",
                ]
            )
            # MacroProbabilities は dict[str, Decimal] サブクラスなので
            # そのまま渡せる。空 dict 縮退時は素の dict を渡す。
            polymarket_macro: dict[str, Decimal] = dict(polymarket_macro_raw)
        except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退
            st.warning(
                f"⚠️ Polymarket 取得失敗: {type(exc).__name__}、"
                "空 dict で続行"
            )
            polymarket_macro = {}

        # ----- Step 2: SEC EDGAR 13F QoQ 差分 (全 ticker 共通 view) -----
        # extract_holdings_delta は ticker 単位で fund 別 delta を返す。
        # signal_aggregator は全銘柄共通の view を期待するため (handoff
        # §2.3、Phase 6 で per-ticker view に拡張予定)、代表 ticker
        # ("SPY") で 1 回だけ取得する素朴な実装に従う (design.md L1368)。
        fund_holdings_delta: dict[str, dict[str, object]] = {}
        try:
            from src.data.sec_edgar import (  # noqa: PLC0415
                SECEdgarClient,
            )
            from src.data.sec_edgar_13f_diff import (  # noqa: PLC0415
                extract_holdings_delta,
            )

            if settings.sec_edgar_user_agent:
                sec_edgar_client = SECEdgarClient(
                    user_agent=settings.sec_edgar_user_agent,
                    cache=ParquetCache(base_dir=settings.cache_dir),
                )
                # TODO(Phase 6): per-ticker view に拡張予定 (handoff §2.3)
                # 現在は全銘柄共通の SPY 代替 view を使用
                fund_holdings_delta = extract_holdings_delta(
                    "SPY", sec_client=sec_edgar_client
                )
        except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退
            st.warning(
                f"⚠️ 13F 差分取得失敗: {type(exc).__name__}、"
                "空 dict で続行"
            )
            fund_holdings_delta = {}

        # ----- Step 3: Regime signals (Choppy 縮退で許容) -----
        # 完全な regime 取得は SPY EOD パイプライン未実装のため Phase 6
        # 持ち越し。PRD §FR5 多段縮退として Choppy + 空 state_probs で
        # 続行する (build_signal_bundle 側で吸収される)。
        regime_signals: dict[str, object] = {
            "regime": "Choppy",
            "state_probs": {},
        }

        # ----- Step 4: シグナル束組み立て + Sonnet 呼び出し -----
        try:
            mf_per_ticker = magic_formula_result_to_per_ticker_dict(result)
            tickers_for_sonnet = [r["_ticker_raw"] for r in composite_rows]

            # UI sidebar は ``["US", "TO"]`` を扱うが、aggregate_signals_for_universe
            # は ``Literal["US", "JP"]`` を期待する。"TO" は東証なので "JP" に正規化。
            _exchange_for_sonnet: Literal["US", "JP"] = (
                "JP" if exchange == "TO" else cast(Literal["US"], "US")
            )

            signal_bundles = aggregate_signals_for_universe(
                tickers=tickers_for_sonnet,
                exchange=_exchange_for_sonnet,
                composite_results=composite_results_dict,
                mf_results=mf_per_ticker,
                sentiment_results=sentiment_results_dict,
                momentum_results=momentum_results_dict,
                polymarket_macro=polymarket_macro,
                fund_holdings_delta_by_fund=fund_holdings_delta,
                regime_signals=regime_signals,
            )

            ranking_results = rank_with_claude_batch(
                signal_bundles,
                anthropic_client=anthropic_client,
                cache_dir=Path(settings.cache_dir) / "sonnet_ranking",
                model=settings.sonnet_model,
                model_version=_resolved_sonnet_model_version(),
                ttl_sec=settings.ranking_cache_ttl_sec,
            )
            return ranking_results, signal_bundles
        except Exception as exc:  # noqa: BLE001 — PRD §FR5 多段縮退
            # Phase 6.3 §4.3 派生 (handoff §4.3):
            # classify_api_exception + FALLBACK_REASON_LABELS で
            # SDK 例外クラス名 / status_code の UI 漏洩を抽象化。
            # ranking_judge.rank_single_with_claude 内部の path 1 fallback と
            # 同じ抽象化規律を、バッチ全体失敗の外側 catch にも適用する。
            # 詳細な例外型と status_code は logger.warning で内部記録。
            reason = classify_api_exception(exc)
            status_code = getattr(exc, "status_code", None)
            logger.warning(
                "Claude 判定全体失敗: reason=%s exc_type=%s status_code=%s exc_msg=%s",
                reason,
                type(exc).__name__,
                status_code,
                str(exc),
            )
            label = FALLBACK_REASON_LABELS.get(reason, reason)
            st.error(
                f"🚨 Claude 判定全体失敗 ({label})、"
                "Composite ランキングのみ表示します。"
            )
            return None, None


# compute_mu_for_monte_carlo は Phase 6.3 で ``src/analysis/ranking_judge.py`` に
# 移管した (handoff §4.1 派生、reviewer HIGH-2 解消)。
# RankingSignalBundle owner と同居させることで dashboard 層 → analysis 層への
# 依存方向を正しくし、analysis 層内で完結する純粋変換 helper にした。
