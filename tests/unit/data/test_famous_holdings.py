"""famous_holdings の静的辞書整合性 + バッジ生成の単体テスト。"""

from __future__ import annotations

import pytest

from data.famous_holdings import (
    FAMOUS_HOLDINGS,
    get_famous_owners,
    has_famous_owner,
    render_owner_badges,
)


@pytest.mark.unit
class TestStaticDictionary:
    """辞書の整合性検証。"""

    def test_全エントリが_frozenset_で_immutable(self) -> None:
        for owners in FAMOUS_HOLDINGS.values():
            assert isinstance(owners, frozenset)

    def test_全達人名が既知の_4_人(self) -> None:
        known_investors = {"Buffett", "Pabrai", "Burry", "Ackman"}
        for owners in FAMOUS_HOLDINGS.values():
            assert owners.issubset(known_investors)

    def test_全キーが_ticker_exchange_タプル(self) -> None:
        for key in FAMOUS_HOLDINGS:
            assert isinstance(key, tuple)
            assert len(key) == 2
            ticker, exchange = key
            assert isinstance(ticker, str)
            assert isinstance(exchange, str)
            assert ticker == ticker.upper()  # 大文字統一


@pytest.mark.unit
class TestGetFamousOwners:
    """get_famous_owners の検索ロジック検証。"""

    def test_AAPL_US_は_Buffett(self) -> None:
        owners = get_famous_owners("AAPL", "US")
        assert owners == frozenset({"Buffett"})

    def test_未登録銘柄は空集合(self) -> None:
        owners = get_famous_owners("UNKNOWN", "US")
        assert owners == frozenset()

    def test_小文字_ticker_でも検索可能(self) -> None:
        owners = get_famous_owners("aapl", "us")
        assert owners == frozenset({"Buffett"})

    def test_異なる_exchange_は別銘柄として扱う(self) -> None:
        # AAPL.US は Buffett 保有だが、AAPL.TO は (架空) 別物
        assert get_famous_owners("AAPL", "US") == frozenset({"Buffett"})
        assert get_famous_owners("AAPL", "TO") == frozenset()


@pytest.mark.unit
class TestRenderOwnerBadges:
    """render_owner_badges のバッジ文字列生成検証。"""

    def test_Buffett_保有でバフェット保有バッジ(self) -> None:
        result = render_owner_badges(frozenset({"Buffett"}))
        assert "🐋" in result
        assert "バフェット" in result

    def test_空集合は空文字(self) -> None:
        assert render_owner_badges(frozenset()) == ""

    def test_複数達人で空白区切り(self) -> None:
        result = render_owner_badges(frozenset({"Buffett", "Pabrai"}))
        # sorted なので Buffett (B...) が先、Pabrai (P...) が後
        assert "バフェット" in result
        assert "パブライ" in result
        # 空白区切りで複数バッジ
        assert result.count("🐋") == 2

    def test_未知の名前はそのまま表示(self) -> None:
        # フォールバック動作
        result = render_owner_badges(frozenset({"UnknownInvestor"}))
        assert "UnknownInvestor" in result


@pytest.mark.unit
class TestHasFamousOwner:
    """has_famous_owner の高速判定検証。"""

    def test_保有銘柄は_True(self) -> None:
        assert has_famous_owner("AAPL", "US") is True

    def test_未登録銘柄は_False(self) -> None:
        assert has_famous_owner("UNKNOWN", "US") is False
