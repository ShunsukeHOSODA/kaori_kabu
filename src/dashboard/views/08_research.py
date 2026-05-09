"""銘柄リサーチ — ティッカー入力 → 過去検証 + 将来予測 を内部タブで切替。

要件 .steering/20260509-ui-5tab-redesign/ §5。
ティッカー入力 → EODHD で 5 年データ取得 → 内部タブで過去・将来分析。

CLAUDE.md §9.3「一本線予測禁止」/ §9.4「シグナル根拠併記」/ §9.7
「認知バイアス警告」を遵守。Monte Carlo は確率分布のみで「○ 円になります」
は絶対に出さない。

過去検証 (vectorbt フル機能) と Monte Carlo (詳細パラメータ) は元の
04_backtest.py / 05_monte_carlo.py に温存（ナビ非表示で URL 直接アクセス可）。
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config.settings import settings
from src.data.cache import ParquetCache
from src.data.eodhd import EODHDAPIError, EODHDClient
from src.ui.theme import apply_theme

st.set_page_config(
    page_title="銘柄を調べる — kaori_kabu", page_icon="🧪", layout="wide"
)
apply_theme()

st.title("🧪 銘柄を調べる")
st.caption(
    "気になる銘柄のティッカーを入力すると、過去 5 年の値動き分析と将来 1 年の"
    "確率分布を内部タブで確認できます。"
    "**CLAUDE.md §9.3 に基づき一本線予測は出さず、確率分布のみ表示します**。"
)


# ───────────────────────────────────────────────
# 入力フォーム
# ───────────────────────────────────────────────
col_ticker, col_exchange = st.columns([3, 1])
with col_ticker:
    default_ticker = st.query_params.get("ticker", "AAPL")
    ticker_raw = st.text_input(
        "ティッカー",
        value=default_ticker,
        placeholder="例: AAPL（米国） / 7203（東証）",
    )
    ticker = ticker_raw.strip().upper()
with col_exchange:
    exchange = st.selectbox(
        "取引所", ["US", "TO"], index=0, help="US=米国、TO=東証（日本株）"
    )

if not ticker:
    st.info("ティッカーを入力してください")
    st.stop()

if not settings.eodhd_api_key:
    st.error(
        "`EODHD_API_KEY` が `.env` に未設定です。"
        "ホーム画面のサイドバーで API 設定状況を確認してください。"
    )
    st.stop()


# ───────────────────────────────────────────────
# 過去 5 年データ取得（24h キャッシュ）
# ───────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner="📊 過去 5 年データを取得中...")
def _fetch_history(api_key: str, ticker: str, exchange: str) -> pd.DataFrame | None:
    """EODHD で過去 5 年の OHLC を取得。失敗時 None。"""
    try:
        cache = ParquetCache(base_dir=settings.cache_dir)
        client = EODHDClient(api_key=api_key, cache=cache)
        today_local = date.today()
        from_d = today_local - timedelta(days=5 * 365 + 30)
        df = client.get_eod(
            ticker, exchange=exchange, from_date=from_d, to_date=today_local
        )
        if len(df) == 0 or "close" not in df.columns:
            return None
        return df
    except (EODHDAPIError, httpx.HTTPError, KeyError):
        return None


df = _fetch_history(settings.eodhd_api_key, ticker, exchange)
if df is None or len(df) < 100 or "date" not in df.columns:
    st.error(
        f"`{ticker}.{exchange}` の過去データを取得できませんでした"
        "（または 100 日未満のため分析不可）。"
        "ティッカー・取引所を確認してください。"
    )
    st.stop()

# EODHDClient.get_eod は date を **列** として返す（reset_index(drop=True)）
# ため、df.index は int RangeIndex。可視化用に DateTime Series として取り出す。
date_series = pd.to_datetime(df["date"])

st.caption(
    f"📅 期間: {date_series.min().date()} 〜 {date_series.max().date()}"
    f"（{len(df)} 日分、最新終値 {float(df['close'].iloc[-1]):.2f}）"
)


# ───────────────────────────────────────────────
# 内部タブ: 過去検証 / 将来予測
# ───────────────────────────────────────────────
tab_past, tab_future = st.tabs(["📜 過去検証", "🎲 将来予測"])


# ─── 過去検証タブ ───
with tab_past:
    st.subheader(f"📜 {ticker} の過去 5 年の値動きとリスク指標")

    # 価格チャート（x 軸は date 列の DateTime Series）
    fig_price = go.Figure()
    fig_price.add_trace(
        go.Scatter(
            x=date_series,
            y=df["close"],
            name="終値",
            line={"color": "#1f77b4", "width": 1.5},
        )
    )
    fig_price.update_layout(
        height=420,
        xaxis_title="日付",
        yaxis_title="価格",
        hovermode="x unified",
        margin={"l": 40, "r": 20, "t": 30, "b": 40},
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # 性能指標（empyrical-reloaded）
    daily_returns = df["close"].pct_change().dropna()
    if len(daily_returns) >= 252:
        try:
            import empyrical as ep

            cagr = float(ep.cagr(daily_returns))
            sharpe = float(ep.sharpe_ratio(daily_returns))
            sortino = float(ep.sortino_ratio(daily_returns))
            calmar = float(ep.calmar_ratio(daily_returns))
            max_dd = float(ep.max_drawdown(daily_returns))

            st.subheader("📊 リスク指標（5 年）")
            cols = st.columns(5)
            cols[0].metric(
                "年率リターン (CAGR)",
                f"{cagr * 100:.2f}%",
                help="複利での年率成長率。米国株市場の平均は約 7-10%",
            )
            cols[1].metric(
                "Sharpe Ratio",
                f"{sharpe:.2f}",
                help="リスク 1 単位あたりの超過リターン。**1.0 以上で良好、2.0 以上で優秀**",
            )
            cols[2].metric(
                "Sortino Ratio",
                f"{sortino:.2f}",
                help="下方リスクのみで割った Sharpe 改良版。Sharpe より高い数字になりやすい",
            )
            cols[3].metric(
                "Calmar Ratio",
                f"{calmar:.2f}",
                help="CAGR / |Max DD|。**1.0 以上で良好、3.0 以上で優秀**",
            )
            cols[4].metric(
                "最大下落 (Max DD)",
                f"{max_dd * 100:.2f}%",
                help="ピークからの最大ドローダウン。-30% 以下で要注意",
            )
        except (ValueError, ZeroDivisionError, ImportError) as exc:
            st.warning(f"性能指標の計算に失敗: {exc}")
    else:
        st.info("データが 1 年未満のため性能指標を計算できません")

    st.caption(
        "ⓘ より詳細なバックテスト（戦略別、買い持ち vs SMA クロス等）は "
        "Phase 3.3 で実装予定。現状はバイアンドホールドの統計のみ。"
    )


# ─── 将来予測タブ ───
with tab_future:
    st.subheader(f"🎲 {ticker} の 1 年後の確率分布（Monte Carlo GBM 1000 パス）")
    st.caption(
        "**CLAUDE.md §9.3 に基づき一本線予測は出しません**。"
        "5/25/50/75/95 パーセンタイルで「何 % の確率でいくらになるか」を表示。"
        "過去 5 年の日次リターンの平均・標準偏差を Geometric Brownian Motion に投入。"
    )

    daily_returns = df["close"].pct_change().dropna()
    spot = float(df["close"].iloc[-1])
    mu = float(daily_returns.mean())
    sigma = float(daily_returns.std())
    n_days = 252
    n_paths = 1000

    # GBM Monte Carlo（再現性のため固定シード）
    rng = np.random.default_rng(42)
    z = rng.standard_normal((n_paths, n_days))
    daily_log_returns = (mu - 0.5 * sigma**2) + sigma * z
    cumulative = np.exp(daily_log_returns.cumsum(axis=1))
    paths = spot * cumulative

    # 時系列 fan chart
    percentiles = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    last_date = date_series.iloc[-1]
    future_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1), periods=n_days, freq="D"
    )

    fig_mc = go.Figure()
    # 5-95% range (薄い帯)
    fig_mc.add_trace(
        go.Scatter(
            x=future_dates,
            y=percentiles[4],
            name="95%ile",
            line={"color": "rgba(0,0,0,0)"},
            showlegend=False,
        )
    )
    fig_mc.add_trace(
        go.Scatter(
            x=future_dates,
            y=percentiles[0],
            name="5-95% 範囲（90% の可能性）",
            fill="tonexty",
            fillcolor="rgba(31, 119, 180, 0.18)",
            line={"color": "rgba(0,0,0,0)"},
        )
    )
    # 25-75% range (濃い帯)
    fig_mc.add_trace(
        go.Scatter(
            x=future_dates,
            y=percentiles[3],
            name="75%ile",
            line={"color": "rgba(0,0,0,0)"},
            showlegend=False,
        )
    )
    fig_mc.add_trace(
        go.Scatter(
            x=future_dates,
            y=percentiles[1],
            name="25-75% 範囲（50% の可能性）",
            fill="tonexty",
            fillcolor="rgba(31, 119, 180, 0.4)",
            line={"color": "rgba(0,0,0,0)"},
        )
    )
    # Median
    fig_mc.add_trace(
        go.Scatter(
            x=future_dates,
            y=percentiles[2],
            name="中央値（50%ile）",
            line={"color": "#1f77b4", "width": 2.5},
        )
    )
    # 過去 1 年を参考表示（x 軸は date Series）
    last_year_dates = date_series.iloc[-252:]
    last_year_close = df["close"].iloc[-252:]
    fig_mc.add_trace(
        go.Scatter(
            x=last_year_dates,
            y=last_year_close,
            name="過去 1 年（参考）",
            line={"color": "#888888", "dash": "dash", "width": 1.2},
        )
    )
    fig_mc.update_layout(
        height=480,
        xaxis_title="日付",
        yaxis_title="価格",
        hovermode="x unified",
        margin={"l": 40, "r": 20, "t": 30, "b": 40},
        legend={"orientation": "h", "y": -0.15},
    )
    st.plotly_chart(fig_mc, use_container_width=True)

    # 1 年後の予測価格パーセンタイル
    final_prices = paths[:, -1]
    p5, p25, p50, p75, p95 = np.percentile(final_prices, [5, 25, 50, 75, 95])
    st.subheader(f"📊 1 年後（{future_dates[-1].date()}）の予測価格分布")
    cols = st.columns(5)
    cols[0].metric(
        "5%ile（悲観）",
        f"{p5:.2f}",
        f"{(p5 / spot - 1) * 100:+.1f}%",
        help="このシナリオを下回る可能性 5%",
    )
    cols[1].metric(
        "25%ile",
        f"{p25:.2f}",
        f"{(p25 / spot - 1) * 100:+.1f}%",
    )
    cols[2].metric(
        "50%ile（中央）",
        f"{p50:.2f}",
        f"{(p50 / spot - 1) * 100:+.1f}%",
        help="半分はこれより高く、半分はこれより低い",
    )
    cols[3].metric(
        "75%ile",
        f"{p75:.2f}",
        f"{(p75 / spot - 1) * 100:+.1f}%",
    )
    cols[4].metric(
        "95%ile（楽観）",
        f"{p95:.2f}",
        f"{(p95 / spot - 1) * 100:+.1f}%",
        help="このシナリオを上回る可能性 5%",
    )

    st.warning(
        "⚠️ Monte Carlo は **過去のリターン分布が未来も続くと仮定** したシミュレーション。"
        "**実際の将来は予測不可能** — 確率分布として「どのくらい不確実か」を視覚化する道具。\n\n"
        "・**Black Swan**（リーマン級の暴落）は仮定の外\n"
        "・企業固有のニュース（決算・買収）も反映しない\n"
        "・あくまで「もし正規分布通りに動いたら」のシナリオ"
    )
