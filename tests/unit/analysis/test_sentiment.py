"""ニュースセンチメント分析（Claude Haiku 4.5）の単体テスト。

学術根拠:
    Tetlock 2007 "Giving Content to Investor Sentiment"
    Loughran-McDonald 2011 (金融特化センチメント辞書)

テスト方針:
    - anthropic.Anthropic はモック化。実 API は呼ばない。
    - レスポンスは構造化 JSON 文字列を返すよう仕込む。
    - Provenance metadata（model_version / calculation_method /
      input_news_count / academic_source / code_commit）必須。
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_anthropic_mock(json_text: str) -> MagicMock:
    """``anthropic.Anthropic`` を模倣する MagicMock。

    ``messages.create`` の戻り値の ``content[0].text`` に ``json_text`` を
    入れる。
    """
    block = MagicMock()
    block.text = json_text
    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(input_tokens=100, output_tokens=50)

    client = MagicMock()
    client.messages.create.return_value = response
    return client


@pytest.fixture
def sample_news_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "title": "AAPL beats Q1 estimates",
                "snippet": "Apple posted Q1 earnings of $X exceeding estimates",
                "url": "https://example.com/aapl-q1",
                "published_at": pd.Timestamp("2026-04-25", tz="UTC"),
                "source_provider": "Tavily",
            },
            {
                "title": "Apple AI investment ramps",
                "snippet": "Apple announced new AI infrastructure",
                "url": "https://example.com/aapl-ai",
                "published_at": pd.Timestamp("2026-05-02", tz="UTC"),
                "source_provider": "Tavily",
            },
        ]
    )


# ---------------------------------------------------------------------------
# プロンプト構築
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildSentimentPrompt:
    """ニュース DataFrame → user メッセージ文字列。"""

    def test_銘柄名と記事数がプロンプトに含まれる(
        self, sample_news_df: pd.DataFrame
    ) -> None:
        from analysis.sentiment import build_sentiment_user_message

        msg = build_sentiment_user_message(sample_news_df, ticker="AAPL")

        assert "AAPL" in msg
        # 2 件の記事タイトル
        assert "beats Q1" in msg
        assert "AI investment" in msg


# ---------------------------------------------------------------------------
# analyze_sentiment（Claude Haiku モック）
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzeSentiment:
    """Claude Haiku を呼ぶ analyze_sentiment 関数。"""

    def test_JSONレスポンス_SentimentResult構築(
        self, sample_news_df: pd.DataFrame
    ) -> None:
        from analysis.sentiment import SentimentResult, analyze_sentiment

        json_text = """{
            "sentiment_score": 0.65,
            "confidence": 0.85,
            "key_themes": ["earnings beat", "AI investment"],
            "risk_signals": ["regulatory headwind"],
            "summary": "Apple posted strong Q1 with AI tailwind."
        }"""
        client = _make_anthropic_mock(json_text)

        result = analyze_sentiment(
            sample_news_df, ticker="AAPL", anthropic_client=client
        )

        assert isinstance(result, SentimentResult)
        assert result.sentiment_score == Decimal("0.65")
        assert result.confidence == Decimal("0.85")
        assert result.key_themes == ("earnings beat", "AI investment")
        assert result.risk_signals == ("regulatory headwind",)
        assert "Apple" in result.summary

        # API は 1 回だけ呼ばれる
        assert client.messages.create.call_count == 1

    def test_metadata必須フィールドが揃う(
        self, sample_news_df: pd.DataFrame
    ) -> None:
        from analysis.sentiment import (
            SentimentMetadata,
            analyze_sentiment,
        )

        json_text = """{
            "sentiment_score": 0.0,
            "confidence": 0.5,
            "key_themes": [],
            "risk_signals": [],
            "summary": "Mixed signals."
        }"""
        client = _make_anthropic_mock(json_text)

        result = analyze_sentiment(
            sample_news_df, ticker="AAPL", anthropic_client=client
        )

        assert isinstance(result.metadata, SentimentMetadata)
        assert result.metadata.calculation_method == "sentiment_v1"
        assert "Tetlock" in result.metadata.academic_source
        assert result.metadata.input_news_count == len(sample_news_df)
        assert result.metadata.calculated_at.tzinfo is not None
        assert "haiku" in result.metadata.model.lower()

    def test_空DataFrame_中立スコア返却_API呼び出しなし(self) -> None:
        """ニュースが 0 件なら API を呼ばずに中立 (0.0, conf 0.0) を返す。"""
        from analysis.sentiment import analyze_sentiment

        client = _make_anthropic_mock("{}")  # 呼ばれないはず
        empty_df = pd.DataFrame(
            columns=["title", "snippet", "url", "published_at", "source_provider"]
        )

        result = analyze_sentiment(
            empty_df, ticker="AAPL", anthropic_client=client
        )

        assert result.sentiment_score == Decimal("0")
        assert result.confidence == Decimal("0")
        assert result.metadata.input_news_count == 0
        assert client.messages.create.call_count == 0

    def test_JSONがコードブロックで包まれていても抽出できる(
        self, sample_news_df: pd.DataFrame
    ) -> None:
        """Claude が ```json ... ``` で返した場合に対応。"""
        from analysis.sentiment import analyze_sentiment

        json_text = """```json
{
    "sentiment_score": -0.4,
    "confidence": 0.7,
    "key_themes": ["regulatory pressure"],
    "risk_signals": ["FTC investigation"],
    "summary": "Regulatory headwind dominating."
}
```"""
        client = _make_anthropic_mock(json_text)

        result = analyze_sentiment(
            sample_news_df, ticker="AAPL", anthropic_client=client
        )

        assert result.sentiment_score == Decimal("-0.4")
        assert "regulatory pressure" in result.key_themes
