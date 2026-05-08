"""保有銘柄管理（Holding / Portfolio）の単体テスト。

CLAUDE.md §4 / §9.1 / §9.6 に準拠:
    - 金額は Decimal 型
    - 日付は date オブジェクト
    - 口座種別タグ（NISA / 特定 / 旧NISA）必須
    - immutable データ構造（frozen dataclass）
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


def _aapl_holding():
    """テスト用 AAPL 保有データ（合成）。"""
    from portfolio.holdings import Holding

    return Holding(
        ticker="AAPL",
        exchange="US",
        shares=Decimal("10"),
        avg_cost_jpy=Decimal("25000"),
        purchased_at=date(2025, 1, 15),
        account_type="NISA",
    )


def _toyota_holding():
    """テスト用 トヨタ自動車 保有データ（合成、東証）。"""
    from portfolio.holdings import Holding

    return Holding(
        ticker="7203",
        exchange="TO",
        shares=Decimal("100"),
        avg_cost_jpy=Decimal("2800"),
        purchased_at=date(2024, 12, 1),
        account_type="特定",
    )


@pytest.mark.unit
class TestHolding:
    """Holding は frozen dataclass で immutable。"""

    def test_Holding_は_immutable(self) -> None:
        h = _aapl_holding()

        with pytest.raises(FrozenInstanceError):
            h.shares = Decimal("20")  # type: ignore[misc]

    def test_必須フィールドが揃う(self) -> None:
        h = _aapl_holding()

        assert h.ticker == "AAPL"
        assert h.exchange == "US"
        assert h.shares == Decimal("10")
        assert h.avg_cost_jpy == Decimal("25000")
        assert h.purchased_at == date(2025, 1, 15)
        assert h.account_type == "NISA"


@pytest.mark.unit
class TestPortfolio:
    """Portfolio は Holding の集合（immutable）。"""

    def test_total_cost_jpy_合計取得コスト(self) -> None:
        from portfolio.holdings import Portfolio

        p = Portfolio(holdings=(_aapl_holding(), _toyota_holding()))

        # AAPL: 10 * 25000 = 250000
        # 7203: 100 * 2800 = 280000
        assert p.total_cost_jpy() == Decimal("530000")

    def test_by_ticker_存在する銘柄(self) -> None:
        from portfolio.holdings import Portfolio

        p = Portfolio(holdings=(_aapl_holding(), _toyota_holding()))

        h = p.by_ticker("AAPL")

        assert h is not None
        assert h.ticker == "AAPL"

    def test_by_ticker_存在しない銘柄_None(self) -> None:
        from portfolio.holdings import Portfolio

        p = Portfolio(holdings=(_aapl_holding(),))

        assert p.by_ticker("MISSING") is None

    def test_add_は新しい_Portfolio_を返す_immutable(self) -> None:
        from portfolio.holdings import Portfolio

        p1 = Portfolio(holdings=(_aapl_holding(),))
        p2 = p1.add(_toyota_holding())

        # p1 は変わらず、p2 は 2 銘柄
        assert len(p1.holdings) == 1
        assert len(p2.holdings) == 2
        assert p1 is not p2


@pytest.mark.unit
class TestPortfolioCSV:
    """Portfolio の CSV ラウンドトリップ I/O。"""

    def test_to_csv_書き込み_ヘッダ_行構造(self, tmp_path: Path) -> None:
        from portfolio.holdings import Portfolio

        p = Portfolio(holdings=(_aapl_holding(),))
        path = tmp_path / "portfolio.csv"

        p.to_csv(path)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "ticker" in content
        assert "AAPL" in content
        assert "NISA" in content

    def test_from_csv_読み込み(self, tmp_path: Path) -> None:
        from portfolio.holdings import Portfolio

        path = tmp_path / "portfolio.csv"
        path.write_text(
            "ticker,exchange,shares,avg_cost_jpy,purchased_at,account_type\n"
            "AAPL,US,10,25000,2025-01-15,NISA\n"
            "7203,TO,100,2800,2024-12-01,特定\n",
            encoding="utf-8",
        )

        p = Portfolio.from_csv(path)

        assert len(p.holdings) == 2
        aapl = p.by_ticker("AAPL")
        assert aapl is not None
        assert aapl.shares == Decimal("10")
        assert aapl.avg_cost_jpy == Decimal("25000")
        assert aapl.purchased_at == date(2025, 1, 15)
        assert aapl.account_type == "NISA"
        toyota = p.by_ticker("7203")
        assert toyota is not None
        assert toyota.exchange == "TO"

    def test_round_trip_CSV(self, tmp_path: Path) -> None:
        """書き込み → 読み込み でデータが完全一致。"""
        from portfolio.holdings import Portfolio

        original = Portfolio(holdings=(_aapl_holding(), _toyota_holding()))
        path = tmp_path / "portfolio.csv"

        original.to_csv(path)
        loaded = Portfolio.from_csv(path)

        assert len(loaded.holdings) == 2
        aapl_loaded = loaded.by_ticker("AAPL")
        aapl_orig = original.by_ticker("AAPL")
        assert aapl_loaded == aapl_orig

    def test_存在しないファイル_空Portfolio(self, tmp_path: Path) -> None:
        """portfolio.csv が無い場合は空 Portfolio を返す（初回起動対応）。"""
        from portfolio.holdings import Portfolio

        path = tmp_path / "nonexistent.csv"

        p = Portfolio.from_csv(path)

        assert len(p.holdings) == 0
        assert p.total_cost_jpy() == Decimal("0")
