"""設定ページ — API キー設定状況・戦略パラメータ確認（素人向け説明付き）。"""

from __future__ import annotations

import streamlit as st

from src.config.settings import settings

st.set_page_config(page_title="設定 — kaori_kabu", page_icon="⚙️", layout="wide")

st.title("⚙️ 設定")
st.caption("API キー設定状況と戦略パラメータを確認（編集は `.env` で行う）")

st.subheader("🔑 API 設定状況")
st.caption(
    "❌ がついている API キーは `.env` ファイルに追記してください。"
    "未設定でも基本機能（モンテカルロ・割安銘柄探し）は動作します。",
)

# 各 API の役割と取得先 URL
api_keys = {
    "EODHD": (
        "EODHD_API_KEY",
        settings.eodhd_api_key,
        "https://eodhd.com",
        "米国・日本株の終値（EOD）取得",
    ),
    "J-Quants": (
        "JQUANTS_REFRESH_TOKEN",
        settings.jquants_refresh_token,
        "https://jpx-jquants.com",
        "JPX 公式の日本株データ（東証ファンダ正本）",
    ),
    "SEC EDGAR": (
        "SEC_EDGAR_USER_AGENT",
        settings.sec_edgar_user_agent,
        "https://www.sec.gov/edgar",
        "達人投資家追従（13F 提出書類）取得",
    ),
    "FRED": (
        "FRED_API_KEY",
        settings.fred_api_key,
        "https://fred.stlouisfed.org/docs/api/api_key.html",
        "米マクロ経済指標（金利・失業率・CPI 等）",
    ),
    "e-Stat": (
        "ESTAT_APP_ID",
        settings.estat_app_id,
        "https://www.e-stat.go.jp/api/",
        "日本政府統計（CPI・GDP・失業率）",
    ),
}

for name, (var, value, url, role) in api_keys.items():
    col1, col2, col3, col4 = st.columns([1, 2, 3, 3])
    with col1:
        if value:
            st.success(f"✅ {name}")
        else:
            st.error(f"❌ {name}")
    with col2:
        st.caption(role)
    with col3:
        st.code(var)
    with col4:
        st.link_button(f"{name} 取得ページ", url)

st.divider()

st.subheader("📐 戦略パラメータ（読み取り専用 — `.env` で変更）")
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 📊 割安銘柄探し（マジックフォーミュラ）")
    st.metric(
        "最低時価総額 (USD)",
        f"${settings.mf_min_market_cap_usd:,}",
        help="この時価総額未満の小型株は除外（流動性確保のため）",
    )
    st.metric(
        "除外セクター",
        ", ".join(settings.excluded_sectors_list),
        help="マジックフォーミュラの定石: 金融・公益・エネルギーは資本回転率が異質なので除外",
    )
    st.metric(
        "上位 N 銘柄",
        settings.mf_top_n,
        help="抽出する割安銘柄の数（多いほど分散、少ないほど集中投資）",
    )

    st.markdown("### 💰 半ケリー法（ポジションサイズ算出）")
    st.metric(
        "ケリー係数",
        f"{settings.kelly_fraction:.2f}",
        help="フルケリーは破滅リスク高い。0.5（半ケリー）で安全寄り",
    )
    st.metric(
        "1 銘柄あたり上限",
        f"{settings.kelly_max_position_pct:.1%}",
        help="1 銘柄に資産の何 % までかけるか（破滅回避のキャップ）",
    )
    st.metric(
        "現金準備比率",
        f"{settings.kelly_cash_reserve_pct:.1%}",
        help="暴落時の買い増し弾薬として残す現金の割合",
    )

with col2:
    st.markdown("### 🛑 ATR トレーリングストップ（自動損切り）")
    st.metric(
        "ATR 期間",
        settings.atr_period,
        help="平均的な値動き幅（ATR = Average True Range）の計算日数",
    )
    st.metric(
        "ATR 倍率",
        f"{settings.atr_multiplier:.1f}",
        help="ATR の何倍下落で損切りするか。2.0 が標準",
    )

    st.markdown("### 🎲 モンテカルロ（将来予測）")
    st.metric(
        "シミュレーション回数",
        settings.mc_simulations,
        help="未来パスを何本生成するか。1000 で実用十分",
    )
    st.metric(
        "予測期間",
        f"{settings.mc_horizon_days} 営業日",
        help="252 営業日 ≒ 1 年。126 ≒ 半年、63 ≒ 3 ヶ月",
    )

    st.markdown("### 🚦 市場レジーム（HMM）")
    st.metric(
        "レジーム数",
        settings.hmm_n_states,
        help="判別する状態数。3 = 強気・横ばい・暴落",
    )
    st.metric(
        "学習期間",
        f"{settings.hmm_lookback_days} 営業日",
        help="過去何日分のデータでレジーム判定モデルを学習するか",
    )

st.divider()

st.subheader("💾 キャッシュ TTL（再取得しない期間）")
st.caption("API 呼び出しを抑えるため、データ種別ごとに再取得までの時間を設定")
ttl_data = {
    "EOD（日次株価）": (settings.cache_ttl_eod, "日次更新なので 24h"),
    "ファンダメンタル": (settings.cache_ttl_fundamental, "四半期更新なので 7 日"),
    "13F（達人投資家保有）": (settings.cache_ttl_13f, "四半期 + 45 日遅延なので 90 日"),
    "ニュース": (settings.cache_ttl_news, "短時間で更新されるので 1 時間"),
}
for name, (seconds, reason) in ttl_data.items():
    days = seconds / 86400
    if days >= 1:
        st.write(f"- **{name}**: {days:.0f} 日 — _{reason}_")
    else:
        st.write(f"- **{name}**: {seconds // 3600} 時間 — _{reason}_")

st.divider()

st.subheader("🧠 Obsidian vault 連携")
st.caption("第二の脳（Obsidian）への自動同期パス（CLAUDE.md §13）")
st.code(f"VAULT_PATH={settings.vault_path}")
st.code(f"VAULT_PROJECT_NOTE={settings.vault_project_note}")
