"""ホームページ — 保有銘柄サマリー + 市場信号灯 + 利確/損切りアラート。

CLAUDE.md §4 / §9.5 / §9.6 / §9.7 / 要件
.steering/20260509-ui-5tab-redesign/ に準拠。

セクション構成:
    1. 取得コストサマリー（保有銘柄数 / 合計コスト / NISA 数）
    2. 市場の機嫌（HMM レジーム検出 SPY+VIX → 🟢🟡🔴）
    3. 「最新価格で評価」ボタン → 評価額・含み損益テーブル
    4. ATR トレーリングストップアラート（規律ベース）
    5. 保有銘柄一覧（取得時情報）
    6. 認知バイアス警告

未実装:
    - Sharpe Ratio など追加リスク指標（Step 5 以降）
    - USD/JPY を固定レートから FX API へ（Phase 3.2）
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
import pandas as pd
import streamlit as st

from src.analysis.regime import RegimeResult, detect_regime_with_provenance
from src.analysis.risk_metrics import (
    compute_portfolio_returns,
    compute_risk_metrics,
)
from src.config.settings import settings
from src.dashboard.widgets.atr_alert import evaluate_alert, render_alert_row
from src.dashboard.widgets.regime_signal import render_regime_signal
from src.dashboard.widgets.risk_metrics_panel import render_risk_metrics_panel
from src.data.cache import ParquetCache
from src.data.eodhd import EODHDAPIError, EODHDClient
from src.portfolio.holdings import Portfolio
from src.portfolio.valuation import (
    evaluate_portfolio,
    total_market_value_jpy,
    total_unrealized_pnl_jpy,
)
from src.ui.theme import apply_theme

st.set_page_config(
    page_title="ホーム — kaori_kabu", page_icon="🏠", layout="wide"
)
apply_theme()

st.title("🏠 ホーム — 保有銘柄サマリー")
st.caption("当日の評価額と含み損益を一画面で確認できます。")


@st.cache_data(ttl=300)
def _load_portfolio() -> Portfolio:
    return Portfolio.from_csv(settings.holdings_file)


@st.cache_data(ttl=86400, show_spinner="🌡️ 市場の機嫌を判定中...")
def _detect_market_regime_cached(
    api_key: str, lookback_days: int = 730
) -> RegimeResult | None:
    """SPY + VIX 過去 ~2 年から HMM で Bull / Choppy / Crisis 判定（24h キャッシュ）。

    失敗時は None を返し、信号灯は「判定中」フォールバック表示になる。
    """
    try:
        cache = ParquetCache(base_dir=settings.cache_dir)
        client = EODHDClient(api_key=api_key, cache=cache)
        today_local = date.today()
        from_d = today_local - timedelta(days=lookback_days)
        spy = client.get_eod(
            "SPY", exchange="US", from_date=from_d, to_date=today_local
        )
        vix = client.get_eod(
            "VIX", exchange="INDX", from_date=from_d, to_date=today_local
        )
        # EODHDClient.get_eod は date を **列** として返す（int RangeIndex）。
        # HMM 学習には日付ベースで SPY と VIX を整合させる必要がある。
        if "date" not in spy.columns or "date" not in vix.columns:
            return None
        spy_close = spy.set_index(pd.to_datetime(spy["date"]))["close"]
        vix_close = vix.set_index(pd.to_datetime(vix["date"]))["close"]
        common = spy_close.index.intersection(vix_close.index)
        if len(common) < 100:
            return None
        return detect_regime_with_provenance(
            prices=spy_close.loc[common],
            vix=vix_close.loc[common],
            input_data_source="EODHD",
        )
    except (
        EODHDAPIError,
        httpx.HTTPError,
        KeyError,
        IndexError,
        ValueError,
    ):
        return None


portfolio = _load_portfolio()


# ───────────────────────────────────────────────
# 市場の機嫌（HMM レジーム検出、CLAUDE.md §9.7 認知バイアス対策）
# ───────────────────────────────────────────────
st.subheader("🌡️ 市場の機嫌")
st.caption(
    "S&P500 + VIX の過去 2 年データから HMM で「強気 / 横ばい / 暴落リスク」を統計判定。"
    "**Crisis 時は新規買い停止が規律**（Recency Bias 抑止）"
)
if settings.eodhd_api_key:
    _regime_result = _detect_market_regime_cached(settings.eodhd_api_key)
    render_regime_signal(_regime_result)
else:
    render_regime_signal(None)


# ───────────────────────────────────────────────
# 空ポートフォリオ → 初回登録ガイド
# ───────────────────────────────────────────────
if len(portfolio.holdings) == 0:
    st.info(
        f"保有銘柄がまだ登録されていません。`{settings.holdings_file}` に CSV を配置してください。"
    )
    st.subheader("CSV フォーマット例")
    st.code(
        "ticker,exchange,shares,avg_cost_jpy,purchased_at,account_type\n"
        "AAPL,US,10,25000,2025-01-15,NISA\n"
        "7203,TO,100,2800,2024-12-01,特定\n",
        language="csv",
    )
    st.markdown(
        """
        ### フィールド説明
        - **ticker**: ティッカーシンボル（例 `AAPL`、`7203`）
        - **exchange**: 取引所コード（`US` / `TO` 東証）
        - **shares**: 保有株数
        - **avg_cost_jpy**: 取得平均単価（JPY、米国株は購入時の換算後）
        - **purchased_at**: 取得日（ISO 8601 `YYYY-MM-DD`）
        - **account_type**: 口座種別（`NISA` / `特定` / `旧NISA`）
        """
    )
    st.stop()


# ───────────────────────────────────────────────
# 取得コストサマリー
# ───────────────────────────────────────────────
total_cost = portfolio.total_cost_jpy()
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("保有銘柄", f"{len(portfolio.holdings)} 銘柄")
with col2:
    st.metric("合計取得コスト", f"¥{int(total_cost):,}")
with col3:
    nisa_count = sum(1 for h in portfolio.holdings if h.account_type == "NISA")
    st.metric("NISA 口座", f"{nisa_count} 銘柄")


# ───────────────────────────────────────────────
# 「最新価格で評価」ボタン
# ───────────────────────────────────────────────
st.divider()
st.subheader("📈 最新評価")

evaluate_button = st.button("🔄 最新価格で評価する", type="primary")

if evaluate_button:
    if not settings.eodhd_api_key:
        st.error("EODHD_API_KEY が未設定です（`.env` に追加してください）")
    else:
        with st.spinner("EODHD から最新価格を取得中..."):
            cache = ParquetCache(base_dir=settings.cache_dir)
            client = EODHDClient(api_key=settings.eodhd_api_key, cache=cache)

            today = date.today()
            from_d = today - timedelta(days=10)

            current_prices_jpy: dict[str, Decimal] = {}
            errors: list[str] = []

            for h in portfolio.holdings:
                try:
                    df = client.get_eod(
                        h.ticker,
                        from_date=from_d,
                        to_date=today,
                        exchange=h.exchange,
                    )
                except EODHDAPIError as exc:
                    errors.append(f"{h.ticker}: {exc}")
                    continue
                except httpx.HTTPError as exc:
                    errors.append(f"{h.ticker}: HTTP {type(exc).__name__}")
                    continue

                if len(df) == 0 or "close" not in df.columns:
                    errors.append(f"{h.ticker}: データ無し")
                    continue

                last_close = Decimal(str(df["close"].iloc[-1]))
                # 米国株: USD → JPY 換算（Phase 1 は .env の固定レート、Phase 2 で為替 API）
                if h.exchange == "US":
                    last_close = last_close * Decimal(
                        str(settings.usdjpy_fallback)
                    )
                current_prices_jpy[h.ticker] = last_close

        if errors:
            st.warning(
                "一部銘柄の取得に失敗:\n" + "\n".join(f"- {e}" for e in errors)
            )

        valuations = evaluate_portfolio(
            portfolio, current_prices_jpy=current_prices_jpy
        )

        if valuations:
            mv = total_market_value_jpy(valuations)
            pnl = total_unrealized_pnl_jpy(valuations)
            evaluated_cost = sum(
                (v.shares * v.avg_cost_jpy for v in valuations), Decimal("0")
            )
            pnl_pct = (
                (pnl / evaluated_cost) if evaluated_cost > 0 else Decimal("0")
            )

            ec1, ec2, ec3 = st.columns(3)
            ec1.metric("評価額", f"¥{int(mv):,}")
            ec2.metric(
                "含み損益",
                f"¥{int(pnl):,}",
                delta=f"{float(pnl_pct) * 100:+.2f}%",
            )
            ec3.metric(
                "適用為替（USD/JPY）",
                f"¥{settings.usdjpy_fallback:.2f}",
                help=".env の USDJPY_FALLBACK を使用しています（Phase 2 で為替 API 化予定）。",
            )

            display_df = pd.DataFrame(
                [
                    {
                        "ティッカー": v.ticker,
                        "株数": float(v.shares),
                        "取得平均": f"¥{int(v.avg_cost_jpy):,}",
                        "現在価格": f"¥{float(v.current_price_jpy):,.0f}",
                        "評価額": f"¥{int(v.market_value_jpy):,}",
                        "含み損益": f"¥{int(v.unrealized_pnl_jpy):,}",
                        "損益率": f"{float(v.unrealized_pnl_pct) * 100:+.2f}%",
                    }
                    for v in valuations
                ]
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # ───────────────────────────────────────────────
            # 📊 リスク指標（Phase 3.2 / CLAUDE.md §9.8 Provenance）
            # 評価できた銘柄全体のポートフォリオレベルでの過去 1 年指標。
            # 失敗（404 / データ不足 / 計算不能）はすべて UI に明示する。
            # ───────────────────────────────────────────────
            st.divider()
            st.subheader("📊 リスク指標")
            st.caption(
                "保有ポートフォリオの**過去 1 年**の指標。"
                "**1 銘柄ごと**ではなく**保有比率で混ぜたポートフォリオ全体**の数字"
            )

            one_year_ago = today - timedelta(days=370)
            prices_by_ticker: dict[str, pd.Series] = {}
            for v in valuations:
                _h = portfolio.by_ticker(v.ticker)
                if _h is None:
                    continue
                try:
                    df_year = client.get_eod(
                        v.ticker,
                        from_date=one_year_ago,
                        to_date=today,
                        exchange=_h.exchange,
                    )
                except (EODHDAPIError, httpx.HTTPError):
                    continue
                if (
                    "date" not in df_year.columns
                    or "close" not in df_year.columns
                    or len(df_year) < 30
                ):
                    continue
                prices_by_ticker[v.ticker] = pd.Series(
                    df_year["close"].astype(float).values,
                    index=pd.to_datetime(df_year["date"]),
                    name=v.ticker,
                )

            if not prices_by_ticker:
                st.info(
                    "リスク指標計算に必要な過去 1 年データを取得できませんでした"
                    "（最低 30 営業日必要）"
                )
            else:
                _valid_v = [v for v in valuations if v.ticker in prices_by_ticker]
                _total_mv = sum(
                    (v.market_value_jpy for v in _valid_v), Decimal("0")
                )
                if _total_mv == Decimal("0"):
                    st.info("評価額が 0 のためリスク指標を計算できません。")
                else:
                    weights = {
                        v.ticker: v.market_value_jpy / _total_mv
                        for v in _valid_v
                    }
                    try:
                        portfolio_returns = compute_portfolio_returns(
                            prices_by_ticker, weights
                        )
                        metrics = compute_risk_metrics(
                            portfolio_returns, input_data_source="EODHD"
                        )
                        render_risk_metrics_panel(metrics)
                    except (ValueError, ZeroDivisionError) as exc:
                        st.warning(f"リスク指標計算エラー: {exc}")

            # ───────────────────────────────────────────────
            # ATR トレーリングストップアラート（CLAUDE.md §9.5 / §9.7）
            # 規律ベース表現で「指示」ではなく「条件到達 + 根拠」を提示
            # ───────────────────────────────────────────────
            st.divider()
            st.subheader("⚠️ 利確 / 損切りアラート")
            st.caption(
                "ATR トレーリングストップ条件を全保有銘柄に機械的に適用。"
                "**判断は規律で**（Loss Aversion 抑止）"
            )

            atr_alerts = []
            for h in portfolio.holdings:
                try:
                    df_atr = client.get_eod(
                        h.ticker,
                        from_date=today - timedelta(days=90),
                        to_date=today,
                        exchange=h.exchange,
                    )
                except (EODHDAPIError, httpx.HTTPError):
                    continue

                if (
                    len(df_atr) < 14
                    or "high" not in df_atr.columns
                    or "low" not in df_atr.columns
                    or "close" not in df_atr.columns
                ):
                    continue

                last_close = Decimal(str(df_atr["close"].iloc[-1]))
                currency = "USD" if h.exchange == "US" else "JPY"

                try:
                    atr_alerts.append(
                        evaluate_alert(
                            h.ticker,
                            df_atr[["high", "low", "close"]],
                            last_close,
                            currency=currency,
                        )
                    )
                except (KeyError, ValueError):
                    continue

            # breach → near → safe の順で表示。safe は折りたたみ
            _priority = {"breach": 0, "near": 1, "safe": 2}
            atr_alerts.sort(key=lambda a: _priority[a.status])

            warning_alerts = [a for a in atr_alerts if a.status != "safe"]
            safe_alerts = [a for a in atr_alerts if a.status == "safe"]

            if warning_alerts:
                for alert in warning_alerts:
                    render_alert_row(alert)
            elif atr_alerts:
                st.success(
                    "🟢 全銘柄が ATR トレーリングストップの安全圏にあります"
                )
            else:
                st.info(
                    "ATR 計算に必要な OHLC データを取得できませんでした"
                    "（90 日分・最低 14 日必要）"
                )

            if safe_alerts:
                with st.expander(f"✅ 安全圏 {len(safe_alerts)} 銘柄（折りたたみ）"):
                    for alert in safe_alerts:
                        render_alert_row(alert)
else:
    st.info(
        "「🔄 最新価格で評価する」を押すと EODHD から最新価格を取得します"
        "（24h キャッシュ）"
    )


# ───────────────────────────────────────────────
# 保有銘柄一覧（取得時情報）
# ───────────────────────────────────────────────
st.divider()
st.subheader("📊 保有銘柄一覧（取得時）")

holdings_df = pd.DataFrame(
    [
        {
            "ティッカー": h.ticker,
            "取引所": h.exchange,
            "株数": float(h.shares),
            "取得平均単価": f"¥{int(h.avg_cost_jpy):,}",
            "取得日": h.purchased_at.isoformat(),
            "口座": h.account_type,
            "取得コスト": f"¥{int(h.shares * h.avg_cost_jpy):,}",
        }
        for h in portfolio.holdings
    ]
)
st.dataframe(holdings_df, use_container_width=True, hide_index=True)


# ───────────────────────────────────────────────
# リスク警告（CLAUDE.md §9.7）
# ───────────────────────────────────────────────
st.divider()
st.warning(
    "⚠️ **認知バイアス対策**\n\n"
    "- **Loss Aversion**: 含み損銘柄を見て焦って売らない（**上記 ATR アラートに従う**）\n"
    "- **Confirmation Bias**: 良い数字だけ見ない、反対意見も検討する\n"
    "- **Recency Bias**: 直近 1 ヶ月の動きより 5 年以上の長期パフォーマンスで判断"
    "（**上記の市場の機嫌信号灯も参考に**）"
)
