"""FinanceDatabase 経由 日本株ユニバース取得の単体テスト（§4.5、handoff-phase4.md）。

JerBouma/FinanceDatabase（無料）から TSE 銘柄リストを取得し、
時価総額カテゴリ別にフィルタしてティッカー文字列リストを返す。

設計判断:
    - market_cap は数値ではなく "Mega Cap" / "Large Cap" / ... の文字列分類
    - TOPIX 公式分類 (Core30 / Large70 / Mid400) と直接対応しないため、
      米国基準分類を流用して TOPIX 近似として提供
    - ティッカー形式は "7203.T" → "7203" に正規化（02_screener の慣習に合わせる）
    - 外部依存（FinanceDatabase）は依存性注入で差し替え可能
"""

from __future__ import annotations

import pandas as pd
import pytest


def _make_mock_jp_df() -> pd.DataFrame:
    """テスト用合成 TSE 銘柄 DataFrame（FinanceDatabase 形式）。"""
    return pd.DataFrame(
        {
            "name": [
                "Toyota Motor",
                "Sony Group",
                "Keyence",
                "Mid Co",
                "Small Co",
                "Micro Co",
            ],
            "exchange": ["JPX", "JPX", "JPX", "JPX", "JPX", "JPX"],
            "market_cap": [
                "Mega Cap",
                "Large Cap",
                "Large Cap",
                "Mid Cap",
                "Small Cap",
                "Micro Cap",
            ],
            "country": ["Japan", "Japan", "Japan", "Japan", "Japan", "Japan"],
        },
        index=pd.Index(
            ["7203.T", "6758.T", "6861.T", "1234.T", "5678.T", "9999.T"],
            name="symbol",
        ),
    )


class _MockEquities:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def select(self, **_kwargs: object) -> pd.DataFrame:
        return self._df


def _factory_for(df: pd.DataFrame):
    def _factory() -> _MockEquities:
        return _MockEquities(df)
    return _factory


@pytest.mark.unit
class TestGetJpUniverse:
    """FinanceDatabase から TSE 銘柄ユニバースをカテゴリ別に取得。"""

    def test_large_cap_filter_はMegaとLargeを返す(self) -> None:
        from data.financedatabase_client import get_jp_universe

        tickers = get_jp_universe(
            cap_filter="large",
            limit=100,
            equities_factory=_factory_for(_make_mock_jp_df()),
        )

        # Mega Cap (7203) + Large Cap (6758, 6861) = 3 銘柄
        assert sorted(tickers) == ["6758", "6861", "7203"]

    def test_mid_cap_filter_はMegaとLargeとMidを返す(self) -> None:
        from data.financedatabase_client import get_jp_universe

        tickers = get_jp_universe(
            cap_filter="mid",
            limit=100,
            equities_factory=_factory_for(_make_mock_jp_df()),
        )

        # Mega + Large + Mid = 4 銘柄
        assert sorted(tickers) == ["1234", "6758", "6861", "7203"]

    def test_all_filter_は全TSE銘柄を返す(self) -> None:
        from data.financedatabase_client import get_jp_universe

        tickers = get_jp_universe(
            cap_filter="all",
            limit=100,
            equities_factory=_factory_for(_make_mock_jp_df()),
        )

        assert len(tickers) == 6
        assert "7203" in tickers
        assert "9999" in tickers  # Micro Cap も含まれる

    def test_limit_で件数が制限される(self) -> None:
        from data.financedatabase_client import get_jp_universe

        tickers = get_jp_universe(
            cap_filter="all",
            limit=2,
            equities_factory=_factory_for(_make_mock_jp_df()),
        )

        assert len(tickers) == 2

    def test_ticker_format_は4桁数字に正規化される(self) -> None:
        """'7203.T' / '6758.T' → '7203' / '6758' に変換。"""
        from data.financedatabase_client import get_jp_universe

        tickers = get_jp_universe(
            cap_filter="large",
            limit=100,
            equities_factory=_factory_for(_make_mock_jp_df()),
        )

        # 全てが 4 桁数字（.T サフィックスなし）
        for t in tickers:
            assert t.isdigit()
            assert len(t) == 4

    def test_不正なcap_filter_でValueError(self) -> None:
        from data.financedatabase_client import get_jp_universe

        with pytest.raises(ValueError, match="cap_filter"):
            get_jp_universe(
                cap_filter="invalid",  # type: ignore[arg-type]
                limit=100,
                equities_factory=_factory_for(_make_mock_jp_df()),
            )
