"""設定ページ — API キー設定状況・パラメータ確認。"""

from __future__ import annotations

import streamlit as st

from src.config.settings import settings

st.set_page_config(page_title="設定 — kaori_kabu", page_icon="⚙️", layout="wide")

st.title("⚙️ 設定")
st.caption("API キー設定状況・戦略パラメータ確認")

st.subheader("🔑 API 設定状況")
api_keys = {
    "EODHD": ("EODHD_API_KEY", settings.eodhd_api_key, "https://eodhd.com"),
    "J-Quants": (
        "JQUANTS_REFRESH_TOKEN",
        settings.jquants_refresh_token,
        "https://jpx-jquants.com",
    ),
    "SEC EDGAR": (
        "SEC_EDGAR_USER_AGENT",
        settings.sec_edgar_user_agent,
        "https://www.sec.gov/edgar",
    ),
    "FRED": (
        "FRED_API_KEY",
        settings.fred_api_key,
        "https://fred.stlouisfed.org/docs/api/api_key.html",
    ),
    "e-Stat": (
        "ESTAT_APP_ID",
        settings.estat_app_id,
        "https://www.e-stat.go.jp/api/",
    ),
}

for name, (var, value, url) in api_keys.items():
    col1, col2, col3 = st.columns([2, 3, 3])
    with col1:
        if value:
            st.success(f"✅ {name}")
        else:
            st.error(f"❌ {name}")
    with col2:
        st.code(var)
    with col3:
        st.link_button(f"{name} 取得ページ", url)

st.divider()

st.subheader("📐 戦略パラメータ（読み取り専用）")
col1, col2 = st.columns(2)
with col1:
    st.markdown("### Magic Formula")
    st.metric("最低時価総額 (USD)", f"${settings.mf_min_market_cap_usd:,}")
    st.metric("除外セクター", ", ".join(settings.excluded_sectors_list))
    st.metric("上位 N 銘柄", settings.mf_top_n)

    st.markdown("### Half-Kelly")
    st.metric("Kelly Fraction", f"{settings.kelly_fraction:.2f}")
    st.metric("1 銘柄上限", f"{settings.kelly_max_position_pct:.1%}")
    st.metric("現金準備", f"{settings.kelly_cash_reserve_pct:.1%}")

with col2:
    st.markdown("### ATR ストップ")
    st.metric("ATR 期間", settings.atr_period)
    st.metric("ATR 倍率", f"{settings.atr_multiplier:.1f}")

    st.markdown("### Monte Carlo")
    st.metric("シミュレーション数", settings.mc_simulations)
    st.metric("ホライズン", f"{settings.mc_horizon_days} 営業日")

    st.markdown("### HMM レジーム")
    st.metric("状態数", settings.hmm_n_states)
    st.metric("学習期間", f"{settings.hmm_lookback_days} 営業日")

st.divider()

st.subheader("💾 キャッシュ TTL")
ttl_data = {
    "EOD": settings.cache_ttl_eod,
    "ファンダメンタル": settings.cache_ttl_fundamental,
    "13F": settings.cache_ttl_13f,
    "ニュース": settings.cache_ttl_news,
}
for name, seconds in ttl_data.items():
    days = seconds / 86400
    if days >= 1:
        st.write(f"- **{name}**: {days:.0f} 日")
    else:
        st.write(f"- **{name}**: {seconds // 3600} 時間")

st.divider()

st.subheader("🧠 Obsidian vault 連携")
st.code(f"VAULT_PATH={settings.vault_path}")
st.code(f"VAULT_PROJECT_NOTE={settings.vault_project_note}")
