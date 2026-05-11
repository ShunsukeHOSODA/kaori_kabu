"""tests/unit/analysis/ 配下の共通 fixture。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest


@pytest.fixture
def make_bundle() -> Callable[..., object]:
    """RankingSignalBundle の標準 fixture。

    ticker / regime / composite_score を可変に指定可能。他のフィールドは
    Bull regime + Tech sector + Magic Formula 高スコアのデフォルト値で固定。

    Returns:
        ``_make`` 関数。呼び出すと :class:`RankingSignalBundle` のインスタンスを返す。
    """
    from src.analysis.ranking_judge import RankingSignalBundle

    def _make(
        ticker: str = "AAPL",
        regime: str = "Bull",
        composite_score: float = 72.5,
    ) -> object:
        return RankingSignalBundle(
            ticker=ticker,
            exchange="US",
            sector="Technology",
            composite_score=composite_score,
            sub_scores={"Q": 90, "V": 50, "I": 30, "G": 60, "R": 80, "M": 70, "S": 55},
            composite_preset="Buffett_型_暫定",
            magic_formula_score=85.0,
            roc_pct=Decimal("32.5"),
            earnings_yield_pct=Decimal("8.2"),
            momentum_1m=Decimal("3.2"),
            momentum_12m=Decimal("28.5"),
            sentiment_score=Decimal("0.4"),
            sentiment_confidence=Decimal("0.7"),
            sentiment_themes=("iPhone 出荷",),
            polymarket_macro={"fed_cut_2026": Decimal("0.62")},
            fund_holdings_delta={
                "Berkshire": {"action": "NEW", "value_change_usd": 5_200_000_000}
            },
            regime=regime,  # type: ignore[arg-type]
            regime_state_probs={
                "Bull": Decimal("0.6"),
                "Choppy": Decimal("0.3"),
                "Crisis": Decimal("0.1"),
            },
            fetched_at=datetime.now(UTC),
        )

    return _make
