"""世界一の投資家レンズの単体テスト（CLAUDE.md §5 / Phase 2 拡張）。

8 レンズ（Buffett-Munger / Soros / Druckenmiller / Dalio / Pabrai / Burry /
Ackman / Lynch）が「Tavily の 4 系統では拾いきれない投資家視座」を
クエリ展開で補完する。

テスト方針:
    - レンズ定数の網羅性（8 レンズ + rationale + queries 必須）
    - apply_lenses が NewsClient.fetch_geopolitical_news / fetch_research を
      レンズ数分呼ぶこと（モック化）
    - 戻り値 DataFrame に lens_name 列があり、レンズ名で絞れること
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# レンズ定数
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInvestorLensCatalog:
    """``INVESTOR_LENSES`` カタログが 8 レンズ + 必須属性を持つ。"""

    def test_8レンズが揃う(self) -> None:
        from analysis.investor_lenses import INVESTOR_LENSES

        expected = {
            "Buffett_Munger",
            "Soros",
            "Druckenmiller",
            "Dalio",
            "Pabrai",
            "Burry",
            "Ackman",
            "Lynch",
        }
        assert set(INVESTOR_LENSES.keys()) == expected

    def test_各レンズにrationaleとqueriesが必須(self) -> None:
        from analysis.investor_lenses import INVESTOR_LENSES, InvestorLens

        for name, lens in INVESTOR_LENSES.items():
            assert isinstance(lens, InvestorLens), f"{name} not InvestorLens"
            assert lens.rationale, f"{name} missing rationale"
            assert lens.queries, f"{name} missing queries"
            assert isinstance(lens.queries, tuple)


# ---------------------------------------------------------------------------
# apply_lenses（NewsClient と統合）
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyLenses:
    """``apply_lenses`` は指定レンズに応じてクエリを実行し DataFrame 統合。"""

    def test_2レンズ指定_NewsClient呼び出し回数(self) -> None:
        """Buffett_Munger と Burry を指定 → それぞれの queries 数だけ
        ``fetch_geopolitical_news`` または ``fetch_research`` が呼ばれる。
        """
        from analysis.investor_lenses import INVESTOR_LENSES, apply_lenses

        # NewsClient のモック
        mock_client = MagicMock()
        mock_client.fetch_geopolitical_news.return_value = pd.DataFrame(
            {"title": ["g1"], "snippet": ["s1"], "url": ["u1"]}
        )
        mock_client.fetch_research.return_value = pd.DataFrame(
            {"title": ["r1"], "snippet": ["s1"], "url": ["u1"]}
        )

        df = apply_lenses(
            mock_client, ticker="AAPL", lenses=("Buffett_Munger", "Burry")
        )

        assert isinstance(df, pd.DataFrame)
        # lens_name 列が必須
        assert "lens_name" in df.columns
        # 適用されたレンズ名のみが含まれる
        assert set(df["lens_name"].unique()) <= {"Buffett_Munger", "Burry"}

        # 各レンズの query 数だけ fetch_* が呼ばれている
        total_queries = sum(
            len(INVESTOR_LENSES[name].queries)
            for name in ("Buffett_Munger", "Burry")
        )
        actual_calls = (
            mock_client.fetch_geopolitical_news.call_count
            + mock_client.fetch_research.call_count
        )
        assert actual_calls == total_queries

    def test_ticker埋め込み_クエリテンプレート展開(self) -> None:
        """``{ticker}`` プレースホルダがティッカーで置換される。"""
        from analysis.investor_lenses import apply_lenses

        captured: list[str] = []

        def capture_geo(query: str, **kwargs: Any) -> pd.DataFrame:
            captured.append(query)
            return pd.DataFrame({"title": [], "snippet": [], "url": []})

        mock_client = MagicMock()
        mock_client.fetch_geopolitical_news.side_effect = capture_geo
        mock_client.fetch_research.return_value = pd.DataFrame(
            {"title": [], "snippet": [], "url": []}
        )

        apply_lenses(mock_client, ticker="MSFT", lenses=("Buffett_Munger",))

        # Buffett_Munger は ticker 依存クエリを持つため "MSFT" が含まれる
        assert any("MSFT" in q for q in captured)

    def test_全レンズ指定_8レンズ分のlens_nameが揃う(self) -> None:
        from analysis.investor_lenses import INVESTOR_LENSES, apply_lenses

        mock_client = MagicMock()
        # ticker 関係なく空 DataFrame を返す
        empty_df = pd.DataFrame({"title": [], "snippet": [], "url": []})
        mock_client.fetch_geopolitical_news.return_value = empty_df
        mock_client.fetch_research.return_value = empty_df

        df = apply_lenses(
            mock_client,
            ticker="AAPL",
            lenses=tuple(INVESTOR_LENSES.keys()),
        )

        # 空 DataFrame を返すケースでも、lens_name 列の存在のみ確認
        assert "lens_name" in df.columns
