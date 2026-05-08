"""ホームページ — 保有銘柄サマリー + 評価額表示（CLAUDE.md §4 / §9.6 / §9.7）。

セッション開始時の自動表示要件:
    - portfolio.csv 読み込み
    - 当日の評価額・含み益損
    - リスク警告（Loss Aversion 対策）

実装段階:
    - Phase 1（本実装）: 取得コストサマリー + 「最新価格で評価」ボタン
    - Phase 2: HMM レジーム / Sharpe Ratio / ATR 抵触警告 / 為替 API
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
import pandas as pd
import streamlit as st

from src.config.settings import settings
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
st.caption("当日の評価額・含み益損を一画面で確認（CLAUDE.md §4）")


@st.cache_data(ttl=300)
def _load_portfolio() -> Portfolio:
    return Portfolio.from_csv(settings.holdings_file)


portfolio = _load_portfolio()


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
    st.metric("保有銘柄数", f"{len(portfolio.holdings)} 銘柄")
with col2:
    st.metric("合計取得コスト", f"¥{int(total_cost):,}")
with col3:
    nisa_count = sum(1 for h in portfolio.holdings if h.account_type == "NISA")
    st.metric("NISA 口座銘柄", f"{nisa_count} 銘柄")


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
                "含み益損",
                f"¥{int(pnl):,}",
                delta=f"{float(pnl_pct) * 100:+.2f}%",
            )
            ec3.metric(
                "USD/JPY (.env 設定値)",
                f"¥{settings.usdjpy_fallback:.2f}",
            )

            display_df = pd.DataFrame(
                [
                    {
                        "ティッカー": v.ticker,
                        "株数": float(v.shares),
                        "取得平均": f"¥{int(v.avg_cost_jpy):,}",
                        "現在価格": f"¥{float(v.current_price_jpy):,.0f}",
                        "評価額": f"¥{int(v.market_value_jpy):,}",
                        "含み益損": f"¥{int(v.unrealized_pnl_jpy):,}",
                        "損益率": f"{float(v.unrealized_pnl_pct) * 100:+.2f}%",
                    }
                    for v in valuations
                ]
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)
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
    "- **Loss Aversion**: 含み損銘柄を見て焦って売らない（ATR ストップに従う、Phase 2）\n"
    "- **Confirmation Bias**: 良い数字だけ見ない、反対意見も検討する\n"
    "- **Recency Bias**: 直近 1 ヶ月の動きより 5 年以上の長期パフォーマンスで判断"
)
