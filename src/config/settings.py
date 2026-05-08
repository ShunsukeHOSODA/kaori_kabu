"""kaori_kabu 設定モジュール — .env から環境変数を読み込み、型検証する。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """プロジェクト全体の設定。pydantic-settings で .env を自動ロード。"""

    # env_file は順に読まれ、後勝ち。グローバル ~/.claude/.env を先に読み、
    # プロジェクトローカル .env で個別にオーバーライドできる構造（Tavily/Exa
    # キーをグローバルに置いて全プロジェクトで共有するパターンに対応）。
    model_config = SettingsConfigDict(
        env_file=(str(Path.home() / ".claude" / ".env"), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== アプリ基本 =====
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    tz: str = Field(default="Asia/Tokyo", alias="TZ")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")

    # ===== ベース通貨 =====
    base_currency: str = Field(default="JPY", alias="BASE_CURRENCY")
    usdjpy_fallback: float = Field(default=150.0, alias="USDJPY_FALLBACK")

    # ===== データソース API キー =====
    eodhd_api_key: str = Field(default="", alias="EODHD_API_KEY")
    jquants_refresh_token: str = Field(default="", alias="JQUANTS_REFRESH_TOKEN")
    jquants_plan: str = Field(default="light", alias="JQUANTS_PLAN")
    sec_edgar_user_agent: str = Field(default="", alias="SEC_EDGAR_USER_AGENT")
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")
    estat_app_id: str = Field(default="", alias="ESTAT_APP_ID")
    polymarket_base_url: str = Field(
        default="https://gamma-api.polymarket.com",
        alias="POLYMARKET_BASE_URL",
    )

    # ===== ニュース取得 (Tavily / Exa) =====
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    exa_api_key: str = Field(default="", alias="EXA_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    rate_limit_tavily: int = Field(default=100, alias="RATE_LIMIT_TAVILY")
    rate_limit_exa: int = Field(default=60, alias="RATE_LIMIT_EXA")
    news_default_days: int = Field(default=30, alias="NEWS_DEFAULT_DAYS")
    news_default_max_results: int = Field(
        default=10, alias="NEWS_DEFAULT_MAX_RESULTS"
    )

    # ===== キャッシュ・ストレージ =====
    cache_dir: Path = Field(default=Path("./data/cache"), alias="CACHE_DIR")
    holdings_file: Path = Field(
        default=Path("./data/holdings/portfolio.csv"),
        alias="HOLDINGS_FILE",
    )
    decision_log_dir: Path = Field(
        default=Path("./data/decision-log"),
        alias="DECISION_LOG_DIR",
    )

    cache_ttl_eod: int = Field(default=86400, alias="CACHE_TTL_EOD")
    cache_ttl_fundamental: int = Field(default=604800, alias="CACHE_TTL_FUNDAMENTAL")
    cache_ttl_13f: int = Field(default=7776000, alias="CACHE_TTL_13F")
    cache_ttl_news: int = Field(default=3600, alias="CACHE_TTL_NEWS")

    # ===== レート制限 =====
    rate_limit_eodhd: int = Field(default=1000, alias="RATE_LIMIT_EODHD")
    rate_limit_jquants: int = Field(default=60, alias="RATE_LIMIT_JQUANTS")
    rate_limit_sec_edgar: int = Field(default=10, alias="RATE_LIMIT_SEC_EDGAR")
    rate_limit_fred: int = Field(default=120, alias="RATE_LIMIT_FRED")

    # ===== Magic Formula パラメータ =====
    mf_min_market_cap_usd: int = Field(default=100_000_000, alias="MF_MIN_MARKET_CAP_USD")
    mf_exclude_sectors: str = Field(default="Financials,Utilities,Energy", alias="MF_EXCLUDE_SECTORS")
    mf_top_n: int = Field(default=30, alias="MF_TOP_N")
    mf_rebalance_quarters: int = Field(default=4, alias="MF_REBALANCE_QUARTERS")

    # ===== Half-Kelly パラメータ =====
    kelly_fraction: float = Field(default=0.5, alias="KELLY_FRACTION")
    kelly_max_position_pct: float = Field(default=0.05, alias="KELLY_MAX_POSITION_PCT")
    kelly_cash_reserve_pct: float = Field(default=0.10, alias="KELLY_CASH_RESERVE_PCT")

    # ===== ATR ストップ パラメータ =====
    atr_period: int = Field(default=14, alias="ATR_PERIOD")
    atr_multiplier: float = Field(default=2.5, alias="ATR_MULTIPLIER")
    trailing_stop_lookback: int = Field(default=20, alias="TRAILING_STOP_LOOKBACK")

    # ===== Monte Carlo パラメータ =====
    mc_simulations: int = Field(default=1000, alias="MC_SIMULATIONS")
    mc_horizon_days: int = Field(default=252, alias="MC_HORIZON_DAYS")

    # ===== HMM レジーム検出 =====
    hmm_n_states: int = Field(default=3, alias="HMM_N_STATES")
    hmm_lookback_days: int = Field(default=504, alias="HMM_LOOKBACK_DAYS")

    # ===== 13F 追跡対象ファンド CIK =====
    tracked_funds_cik: str = Field(
        default="0001067983,0001173334,0001649339,0001336528,0001079114",
        alias="TRACKED_FUNDS_CIK",
    )

    # ===== Obsidian vault 連携 =====
    vault_path: Path = Field(
        default=Path("/Users/kaori/Desktop/Obsidian/HOSODA_2nd_Brain"),
        alias="VAULT_PATH",
    )
    vault_project_note: str = Field(
        default="notes/projects/kaori_kabu.md",
        alias="VAULT_PROJECT_NOTE",
    )

    # ===== 開発フラグ =====
    debug: str = Field(default="", alias="DEBUG")
    dry_run: bool = Field(default=False, alias="DRY_RUN")
    mock_data: bool = Field(default=False, alias="MOCK_DATA")

    @property
    def excluded_sectors_list(self) -> list[str]:
        return [s.strip() for s in self.mf_exclude_sectors.split(",")]

    @property
    def tracked_funds_cik_list(self) -> list[str]:
        return [c.strip() for c in self.tracked_funds_cik.split(",")]

    @property
    def kelly_max_position_decimal(self) -> Decimal:
        return Decimal(str(self.kelly_max_position_pct))


settings = Settings()
