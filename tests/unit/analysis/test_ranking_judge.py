"""ranking_judge.py のユニットテスト — Task 5.2.1 TDD（RED → GREEN）。"""
from __future__ import annotations

import pytest


class TestForbiddenPatterns:
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "text",
        [
            "AAPL は $200 になる",
            "予想値: ¥30,000",
            "5% 上昇予測",
            "目標株価 $180",
            "target price $250",
            "3 ヶ月以内に高値更新",
            "by 6 months target",
            "forecast price $200",
        ],
    )
    def test_禁止パターンを検出(self, text: str) -> None:
        from src.analysis.ranking_judge import contains_forbidden_pattern

        assert contains_forbidden_pattern(text), f"未検出: {text}"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "text",
        [
            "Composite Score 85 は質×価値の観点で魅力的",
            "13F で Berkshire が新規買い、スマートマネー追従の余地",
            "Polymarket の Fed 利下げ確率 62% を踏まえ慎重に",
            "リスク要因として Recency Bias 懸念",
        ],
    )
    def test_正常テキストは検出しない(self, text: str) -> None:
        from src.analysis.ranking_judge import contains_forbidden_pattern

        assert not contains_forbidden_pattern(text), f"誤検出: {text}"
