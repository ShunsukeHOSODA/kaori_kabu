"""Sentiment サブスコア — 既存 SentimentResult を 0-100 にマッピング。

学術根拠:
    Tetlock 2007（既存 SentimentAnalyzer 参照）

設計:
    sentiment_score (-1〜+1) → (s + 1) / 2 × 100 で 0-100 マッピング。
    confidence (0-1) で「中立 50」とブレンド:
        final = 50 + (raw - 50) × confidence
    confidence 1.0 で raw そのまま、confidence 0.0 で 50（中立）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SentimentSubScoreResult:
    sentiment_score: Decimal
    confidence: Decimal
    score: float


def compute_sentiment_subscore(
    *,
    sentiment_score: Decimal,
    confidence: Decimal,
) -> SentimentSubScoreResult:
    """Sentiment サブスコアを計算（0-100）。"""
    s = float(sentiment_score)
    c = max(0.0, min(1.0, float(confidence)))

    raw = (s + 1.0) / 2.0 * 100.0
    raw = max(0.0, min(100.0, raw))

    final = 50.0 + (raw - 50.0) * c
    final = max(0.0, min(100.0, final))

    return SentimentSubScoreResult(
        sentiment_score=sentiment_score,
        confidence=confidence,
        score=final,
    )
