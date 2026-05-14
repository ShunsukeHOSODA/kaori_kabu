"""tests/unit/analysis/ 配下の共通 fixture。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import pytest


@pytest.fixture
def good_response() -> Any:
    """Sonnet 4.6 が返す正常 JSON response の MagicMock 互換オブジェクト。

    Task 5.2.7 / 5.2.8 共通 fixture（rank_single_with_claude /
    rank_with_claude_batch 双方で使用）。
    """

    class _C:
        text = (
            '{"ranking_score": 78, '
            '"recommendation_summary": "Composite 高 + 13F 整合", '
            '"supporting_signals": ["Composite Q=90", "Berkshire NEW position"], '
            '"risk_signals": ["Recency Bias"], '
            '"counter_view": "Burry はマクロ警戒中", '
            '"lens_views": {'
            '"Buffett_Munger": "質×価値良好", '
            '"Burry": "テールリスク懸念", '
            '"Lynch": "消費者目線で堅調"}, '
            '"confidence": 0.72}'
        )

    class _U:
        input_tokens = 1200
        output_tokens = 350
        cache_read_input_tokens = 800

    class _R:
        content = [_C()]
        usage = _U()

    return _R()


# モジュールレベルの sentinel クラス -- kwarg 既定値で "未指定" を判定するために使う。
# None を渡せるフィールド -- sector -- と区別するため、None ではなく独自 sentinel を
# 使用。クラス化することで mypy が ``str | None | type[_Unset]`` のような union
# 型で取り扱え、``type: ignore[arg-type]`` を削減できる。
class _Unset:
    """sentinel 専用クラス。インスタンス化せず、type[_Unset] を比較に使う。"""


# 単一の sentinel 値 -- 型は ``type[_Unset]``
_UNSET: type[_Unset] = _Unset

# fixture kwarg 用の型エイリアス
_SectorArg = str | None | type[_Unset]
_MacroArg = dict[str, Decimal] | type[_Unset]
_HoldingsArg = dict[str, dict[str, object]] | type[_Unset]
_RegimeArg = Literal["Bull", "Choppy", "Crisis"]


@pytest.fixture
def make_bundle() -> Callable[..., object]:
    """RankingSignalBundle の標準 fixture。

    ticker / regime / composite_score / sector / polymarket_macro /
    fund_holdings_delta を可変に指定可能。他のフィールドは
    Bull regime + Tech sector + Magic Formula 高スコアのデフォルト値で固定。

    Returns:
        ``_make`` 関数。呼び出すと :class:`RankingSignalBundle` のインスタンスを返す。
    """
    from src.analysis.ranking_judge import RankingSignalBundle

    def _make(
        ticker: str = "AAPL",
        regime: _RegimeArg = "Bull",
        composite_score: float = 72.5,
        sector: _SectorArg = _UNSET,
        polymarket_macro: _MacroArg = _UNSET,
        fund_holdings_delta: _HoldingsArg = _UNSET,
    ) -> object:
        # _UNSET sentinel を解決 — 各引数の concrete 型に narrowing
        resolved_sector: str | None = (
            "Technology" if sector is _UNSET else sector  # type: ignore[assignment]
        )
        resolved_macro: dict[str, Decimal] = (
            {"fed_cut_2026": Decimal("0.62")}
            if polymarket_macro is _UNSET
            else polymarket_macro  # type: ignore[assignment]
        )
        resolved_holdings: dict[str, dict[str, object]] = (
            {"Berkshire": {"action": "NEW", "value_change_usd": 5_200_000_000}}
            if fund_holdings_delta is _UNSET
            else fund_holdings_delta  # type: ignore[assignment]
        )
        return RankingSignalBundle(
            ticker=ticker,
            exchange="US",
            sector=resolved_sector,
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
            polymarket_macro=resolved_macro,
            fund_holdings_delta=resolved_holdings,
            regime=regime,
            regime_state_probs={
                "Bull": Decimal("0.6"),
                "Choppy": Decimal("0.3"),
                "Crisis": Decimal("0.1"),
            },
            fetched_at=datetime.now(UTC),
        )

    return _make
