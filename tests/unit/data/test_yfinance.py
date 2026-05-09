"""YFinanceClient ユニットテスト — ``yfinance.Ticker`` を MagicMock で置換。

戦略: ``YFinanceClient`` は ``ticker_factory`` 経由で yfinance.Ticker を呼ぶため、
テスト時は MagicMock 工場を注入する。これにより:

- オフライン実行可能
- yfinance の API 変更があってもテストは安定
- EODHD shape との互換性を契約レベルで保証

実 API 接続は ``@pytest.mark.slow`` のテストでのみ確認する。
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------


def _build_mock_ticker(*, with_data: bool = True) -> MagicMock:
    """AAPL ライクなファンダを持つ MagicMock(yfinance.Ticker) を作る。"""
    ticker = MagicMock()
    if not with_data:
        ticker.info = {}
        ticker.income_stmt = pd.DataFrame()
        ticker.balance_sheet = pd.DataFrame()
        ticker.cashflow = pd.DataFrame()
        return ticker

    ticker.info = {
        "longName": "Apple Inc",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "marketCap": 3_500_000_000_000,
        "enterpriseValue": 3_600_000_000_000,
        "ebitda": 134_661_000_000,
        "trailingPE": 30.5,
        "returnOnEquity": 1.5,
        "returnOnAssets": 0.27,
        "dividendRate": 0.96,
        "payoutRatio": 0.16,
        "earningsQuarterlyGrowth": 0.05,
        "fiveYearAvgDividendYield": 0.62,
        "totalCash": 65_000_000_000,
        "totalDebt": 110_000_000_000,
        "sharesOutstanding": 15_000_000_000,
    }
    ticker.income_stmt = pd.DataFrame(
        {
            pd.Timestamp("2024-09-30"): {
                "Operating Income": 119_437_000_000,
                "Total Revenue": 391_035_000_000,
                "EBITDA": 134_661_000_000,
                "Gross Profit": 180_683_000_000,
                "Diluted EPS": 6.08,
            },
            pd.Timestamp("2023-09-30"): {
                "Operating Income": 114_301_000_000,
                "Total Revenue": 383_285_000_000,
                "EBITDA": 125_820_000_000,
                "Gross Profit": 169_148_000_000,
                "Diluted EPS": 6.13,
            },
        }
    )
    ticker.balance_sheet = pd.DataFrame(
        {
            pd.Timestamp("2024-09-30"): {
                "Current Assets": 152_987_000_000,
                "Current Liabilities": 176_392_000_000,
                "Net PPE": 45_680_000_000,
                "Total Assets": 364_980_000_000,
                "Total Liabilities Net Minority Interest": 308_030_000_000,
                "Retained Earnings": -19_154_000_000,
            },
        }
    )
    ticker.cashflow = pd.DataFrame(
        {
            pd.Timestamp("2024-09-30"): {
                "Operating Cash Flow": 118_254_000_000,
                "Capital Expenditure": -9_447_000_000,
                "Repurchase Of Capital Stock": -94_949_000_000,
            },
        }
    )
    return ticker


def _make_factory(ticker: MagicMock | None = None) -> MagicMock:
    """ticker を返す MagicMock 工場。``call_args`` で呼び出しシンボルを検証可能。"""
    return MagicMock(
        return_value=ticker if ticker is not None else _build_mock_ticker()
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestYFinanceClientShape:
    """get_fundamentals が EODHD と同じ dict shape を返すことを契約として検証。"""

    def test_必須キー_General_Highlights_Financials_SharesStats_全てある(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        factory = _make_factory()
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        result = client.get_fundamentals("AAPL")

        for key in ("General", "Highlights", "Financials", "SharesStats"):
            assert key in result, f"{key} が dict に存在しない"

    def test_General_Code_Sector_Industry(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())
        result = client.get_fundamentals("AAPL")

        assert result["General"]["Code"] == "AAPL"
        assert result["General"]["Sector"] == "Technology"
        assert result["General"]["Industry"] == "Consumer Electronics"

    def test_Highlights_時価総額_EV_EBITDA(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())
        result = client.get_fundamentals("AAPL")

        h = result["Highlights"]
        assert h["MarketCapitalization"] == 3_500_000_000_000
        assert h["EnterpriseValue"] == 3_600_000_000_000
        assert h["EBITDA"] == 134_661_000_000

    def test_Income_Statement_yearly_最新年度に_operatingIncome_あり(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())
        result = client.get_fundamentals("AAPL")

        income = result["Financials"]["Income_Statement"]["yearly"]
        assert "2024-09-30" in income
        assert income["2024-09-30"]["operatingIncome"] == 119_437_000_000.0
        assert income["2024-09-30"]["totalRevenue"] == 391_035_000_000.0

    def test_Balance_Sheet_yearly_流動資産_流動負債_PPE(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())
        result = client.get_fundamentals("AAPL")

        balance = result["Financials"]["Balance_Sheet"]["yearly"]["2024-09-30"]
        assert balance["totalCurrentAssets"] == 152_987_000_000.0
        assert balance["totalCurrentLiabilities"] == 176_392_000_000.0
        assert balance["propertyPlantEquipment"] == 45_680_000_000.0


@pytest.mark.unit
class TestYFinanceClientCompatibility:
    """既存 EODHD 用ヘルパーが yfinance dict でも動くことを保証。"""

    def test_extract_magic_formula_row_が_yfinance_dictで動く(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.eodhd import extract_magic_formula_row
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())
        fundamentals = client.get_fundamentals("AAPL")

        row = extract_magic_formula_row(fundamentals, ticker="AAPL")

        assert row is not None
        assert row["ticker"] == "AAPL"
        assert row["ebit"] > 0
        assert row["enterprise_value"] > 0
        assert row["sector"] == "Technology"


@pytest.mark.unit
class TestYFinanceClientCache:
    """ファンダの 7d JSON キャッシュ（CLAUDE.md §9.2）。"""

    def test_2回目はキャッシュから返り_factoryは1回のみ呼ばれる(
        self, tmp_path: Path
    ) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        factory = _make_factory()
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        client.get_fundamentals("AAPL")
        client.get_fundamentals("AAPL")

        assert factory.call_count == 1

    def test_TTL_0_秒で毎回再取得(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        factory = _make_factory()
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        client.get_fundamentals("AAPL", cache_ttl_sec=0)
        client.get_fundamentals("AAPL", cache_ttl_sec=0)

        assert factory.call_count == 2

    def test_キャッシュファイルがJSONで保存される(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())
        client.get_fundamentals("AAPL")

        files = list((tmp_path / "yfinance").glob("fundamentals_AAPL*.json"))
        assert len(files) == 1


@pytest.mark.unit
class TestYFinanceClientSymbolBuilding:
    """exchange パラメータから yfinance シンボル文字列を構築。"""

    def test_US_は無サフィックス(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        factory = _make_factory()
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        client.get_fundamentals("AAPL", exchange="US")
        factory.assert_called_once_with("AAPL")

    def test_TO_は_T_サフィックス_東証(self, tmp_path: Path) -> None:
        """yfinance は東証銘柄を ``7203.T`` の形で扱う。"""
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        factory = _make_factory()
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        client.get_fundamentals("7203", exchange="TO")
        factory.assert_called_once_with("7203.T")


@pytest.mark.unit
class TestYFinanceClientEdgeCases:
    """欠損データに対する安全性。"""

    def test_空dataframeでも落ちず_yearlyが空dict(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        empty_ticker = _build_mock_ticker(with_data=False)
        factory = _make_factory(empty_ticker)
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        result = client.get_fundamentals("PENNY")

        assert result["Financials"]["Income_Statement"]["yearly"] == {}
        assert result["Financials"]["Balance_Sheet"]["yearly"] == {}
        assert result["Financials"]["Cash_Flow"]["yearly"] == {}


@pytest.mark.unit
class TestYFinanceClientBuildScreenerUniverse:
    """複数銘柄ループ → Magic Formula 入力 DataFrame に統合（EODHD 互換）。"""

    def test_3銘柄_統合(self, tmp_path: Path) -> None:
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        factory = _make_factory()
        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=factory)

        df = client.build_screener_universe(["AAPL", "MSFT", "GOOGL"])

        assert len(df) == 3
        assert set(df.columns) >= {
            "ticker",
            "ebit",
            "net_working_capital",
            "net_fixed_assets",
            "enterprise_value",
        }
        assert list(df["ticker"]) == ["AAPL", "MSFT", "GOOGL"]

    def test_sector除外フィルタ(self, tmp_path: Path) -> None:
        """``excluded_sectors`` にマッチする銘柄は除外される。"""
        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())

        df = client.build_screener_universe(
            ["AAPL", "MSFT"], excluded_sectors=("Technology",)
        )

        assert len(df) == 0

    def test_最低時価総額フィルタ(self, tmp_path: Path) -> None:
        """``min_market_cap_usd`` 未満の銘柄は除外される。"""
        from decimal import Decimal

        from data.cache import ParquetCache
        from data.yfinance import YFinanceClient

        cache = ParquetCache(base_dir=tmp_path)
        client = YFinanceClient(cache=cache, ticker_factory=_make_factory())

        df = client.build_screener_universe(
            ["AAPL", "MSFT"],
            min_market_cap_usd=Decimal("10000000000000"),
        )
        assert len(df) == 0

        df_pass = client.build_screener_universe(
            ["AAPL", "MSFT"], min_market_cap_usd=Decimal("100000000")
        )
        assert len(df_pass) == 2


@pytest.mark.slow
class TestYFinanceClientIntegration:
    """実 yfinance 接続テスト。``pytest -m slow`` で実行。"""

    def test_実API_AAPL_get_fundamentals_必須フィールド(
        self, tmp_path: Path
    ) -> None:
        if os.environ.get("KAORI_KABU_SKIP_NETWORK") == "1":
            pytest.skip("network skipped")
        from data.cache import ParquetCache
        from data.eodhd import extract_magic_formula_row
        from data.yfinance import YFinanceClient, make_default_yfinance_client

        cache = ParquetCache(base_dir=tmp_path)
        client: YFinanceClient = make_default_yfinance_client(cache)

        fundamentals = client.get_fundamentals("AAPL")

        # AAPL は実在の大型株なので Magic Formula 行が抽出できる
        row = extract_magic_formula_row(fundamentals, ticker="AAPL")
        assert row is not None
        assert row["ebit"] > 0
        assert row["enterprise_value"] > 0
        assert row["sector"] == "Technology"
