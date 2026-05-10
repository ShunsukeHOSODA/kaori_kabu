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


# ============================================================
# 動的解決経路（SEC EDGAR キャッシュ越し）
# ============================================================


@pytest.mark.unit
class TestFundCikToInvestor:
    """FUND_CIK_TO_INVESTOR 整合性検証。"""

    def test_4_ファンド_4_投資家(self) -> None:
        from data.famous_holdings import FUND_CIK_TO_INVESTOR

        assert len(FUND_CIK_TO_INVESTOR) == 4
        assert set(FUND_CIK_TO_INVESTOR.values()) == {
            "Buffett",
            "Pabrai",
            "Burry",
            "Ackman",
        }

    def test_CIK_は_10桁ゼロ埋め(self) -> None:
        from data.famous_holdings import FUND_CIK_TO_INVESTOR

        for cik in FUND_CIK_TO_INVESTOR:
            assert len(cik) == 10
            assert cik.isdigit()


@pytest.mark.unit
class TestDynamicResolution:
    """SEC EDGAR キャッシュからの動的保有解決。"""

    def _populate_cache(
        self,
        cache,  # ParquetCache
        cik: str,
        issuer_names: list[str],
    ) -> None:
        """指定 CIK 用の 13F キャッシュを準備する補助。"""
        from datetime import datetime, timezone

        import pandas as pd

        from data._provenance import attach_provenance

        df = pd.DataFrame(
            {
                "cik": [cik] * len(issuer_names),
                "report_date": [pd.Timestamp("2025-12-31")] * len(issuer_names),
                "accession_no": ["x"] * len(issuer_names),
                "name_of_issuer": issuer_names,
                "title_of_class": ["COM"] * len(issuer_names),
                "cusip": ["000000000"] * len(issuer_names),
                "value_usd": [1_000_000] * len(issuer_names),
                "shares": [100] * len(issuer_names),
                "share_type": ["SH"] * len(issuer_names),
                "put_call": [None] * len(issuer_names),
                "voting_sole": [100] * len(issuer_names),
                "voting_shared": [0] * len(issuer_names),
                "voting_none": [0] * len(issuer_names),
            }
        )
        attach_provenance(
            df,
            source="SEC EDGAR",
            fetched_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            endpoint="/Archives/.../infoTable.xml",
            params_hash="abc",
        )
        cache.set("SEC_EDGAR", f"13f_{cik}_latest", df)

    def test_キャッシュにあれば動的解決が優先(self, tmp_path) -> None:
        """EDGAR cache に Berkshire 保有として APPLE があれば Buffett を返す。"""
        from data.cache import ParquetCache
        from data.famous_holdings import get_famous_owners

        cache = ParquetCache(base_dir=tmp_path)
        self._populate_cache(
            cache, "0001067983", ["APPLE INC", "BANK OF AMERICA CORP"]
        )

        owners = get_famous_owners("AAPL", "US", cache=cache)
        assert owners == frozenset({"Buffett"})

    def test_複数ファンド保有_動的に統合(self, tmp_path) -> None:
        """同一銘柄を複数ファンドが持つ → 全員返る。"""
        from data.cache import ParquetCache
        from data.famous_holdings import get_famous_owners

        cache = ParquetCache(base_dir=tmp_path)
        self._populate_cache(cache, "0001067983", ["APPLE INC"])
        self._populate_cache(cache, "0001336528", ["APPLE INC"])

        owners = get_famous_owners("AAPL", "US", cache=cache)
        assert owners == frozenset({"Buffett", "Ackman"})

    def test_キャッシュ空なら静的辞書フォールバック(self, tmp_path) -> None:
        """空 cache → 静的辞書から AAPL=Buffett を返す。"""
        from data.cache import ParquetCache
        from data.famous_holdings import get_famous_owners

        cache = ParquetCache(base_dir=tmp_path)
        owners = get_famous_owners("AAPL", "US", cache=cache)
        assert owners == frozenset({"Buffett"})

    def test_非US銘柄は動的経路スキップ(self, tmp_path) -> None:
        """exchange != "US" は動的解決を試みず即フォールバック（空集合）。"""
        from data.cache import ParquetCache
        from data.famous_holdings import get_famous_owners

        cache = ParquetCache(base_dir=tmp_path)
        self._populate_cache(cache, "0001067983", ["APPLE INC"])

        owners = get_famous_owners("AAPL", "TO", cache=cache)
        assert owners == frozenset()

    def test_TICKER_TO_ISSUER_NAME不在_は動的経路スキップ(
        self, tmp_path
    ) -> None:
        """マップに無い ticker は動的解決スキップ → 静的辞書フォールバック。"""
        from data.cache import ParquetCache
        from data.famous_holdings import get_famous_owners

        cache = ParquetCache(base_dir=tmp_path)
        self._populate_cache(cache, "0001067983", ["APPLE INC"])

        owners = get_famous_owners("UNKNOWN_TICKER", "US", cache=cache)
        assert owners == frozenset()

    def test_動的にヒットしなければ静的辞書フォールバック(
        self, tmp_path
    ) -> None:
        """cache にデータはあるが当該 ticker 該当なし → 静的辞書フォールバック。"""
        from data.cache import ParquetCache
        from data.famous_holdings import get_famous_owners

        cache = ParquetCache(base_dir=tmp_path)
        self._populate_cache(cache, "0001067983", ["COCA COLA CO"])

        # AAPL は動的では未ヒット、静的辞書で Buffett
        owners = get_famous_owners("AAPL", "US", cache=cache)
        assert owners == frozenset({"Buffett"})


@pytest.mark.unit
class TestTickerToIssuerName:
    """TICKER_TO_ISSUER_NAME の整合性検証。"""

    def test_全静的辞書ティッカーがマップ済み(self) -> None:
        """FAMOUS_HOLDINGS の全 US ティッカーが TICKER_TO_ISSUER_NAME 登録済み。"""
        from data.famous_holdings import FAMOUS_HOLDINGS, TICKER_TO_ISSUER_NAME

        for ticker, exchange in FAMOUS_HOLDINGS:
            if exchange == "US":
                assert ticker in TICKER_TO_ISSUER_NAME, (
                    f"{ticker} missing from TICKER_TO_ISSUER_NAME"
                )

    def test_全issuer_name_が大文字(self) -> None:
        from data.famous_holdings import TICKER_TO_ISSUER_NAME

        for issuer_name in TICKER_TO_ISSUER_NAME.values():
            assert issuer_name == issuer_name.upper()
