"""売買判断ログ（Decision Log）の単体テスト。

CLAUDE.md §9.5 / §9.8.3 に準拠:
    - append-only JSONL 形式（``data/decision-log/{YYYY-MM}.jsonl``）
    - 必須フィールド: timestamp, action, ticker, shares, price_jpy,
      rationale, trigger, stop_loss_atr_jpy, code_commit
    - Provenance 込み（後で「なぜ買ったか」を完全再現）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


@pytest.mark.unit
class TestAppendDecision:
    """売買判断を Decision Log に追記。"""

    def test_BUY_判断_書き込み_必須フィールド(self, tmp_path: Path) -> None:
        from portfolio.decision_log import append_decision

        log_path = append_decision(
            log_dir=tmp_path,
            action="BUY",
            ticker="AAPL",
            shares=Decimal("10"),
            price_jpy=Decimal("25000"),
            rationale="Magic Formula スコア 87/100, ROC 28%",
            trigger={"skill": "magic-formula-screener", "score": 87},
            stop_loss_atr_jpy=Decimal("22500"),
            code_commit="edabbe1",
        )

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])

        assert record["action"] == "BUY"
        assert record["ticker"] == "AAPL"
        assert record["shares"] == "10"
        assert record["price_jpy"] == "25000"
        assert "Magic Formula" in record["rationale"]
        assert record["trigger"]["skill"] == "magic-formula-screener"
        assert record["stop_loss_atr_jpy"] == "22500"
        assert record["code_commit"] == "edabbe1"
        ts = datetime.fromisoformat(record["timestamp"])
        assert ts.tzinfo is not None

    def test_append_only_2件追加(self, tmp_path: Path) -> None:
        """同じ月のログに 2 件追加すると JSONL 2 行になる。"""
        from portfolio.decision_log import append_decision

        append_decision(
            log_dir=tmp_path,
            action="BUY",
            ticker="AAPL",
            shares=Decimal("10"),
            price_jpy=Decimal("25000"),
            rationale="first",
        )
        append_decision(
            log_dir=tmp_path,
            action="SELL",
            ticker="MSFT",
            shares=Decimal("5"),
            price_jpy=Decimal("60000"),
            rationale="ATR ストップヒット",
        )

        yyyymm = datetime.now(timezone.utc).strftime("%Y-%m")
        log_path = tmp_path / f"{yyyymm}.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")

        assert len(lines) == 2
        rec1 = json.loads(lines[0])
        rec2 = json.loads(lines[1])
        assert rec1["action"] == "BUY"
        assert rec2["action"] == "SELL"

    def test_オプショナルフィールド省略可(self, tmp_path: Path) -> None:
        """trigger / stop_loss / code_commit / news_context を省略しても動く。"""
        from portfolio.decision_log import append_decision

        log_path = append_decision(
            log_dir=tmp_path,
            action="HOLD",
            ticker="AAPL",
            shares=Decimal("0"),
            price_jpy=Decimal("0"),
            rationale="待機",
        )

        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert record["action"] == "HOLD"
        assert record["trigger"] is None
        assert record["stop_loss_atr_jpy"] is None
        assert record["code_commit"] is None
        assert record["news_context"] is None

    def test_news_context埋め込み(self, tmp_path: Path) -> None:
        """売買時にニュースコンテキスト（センチメント + 要約 + ソース URL）
        が JSONL に保存される（CLAUDE.md §9.5 / Phase 2 要件）。

        後で「なぜ買ったか」を news_context まで含めて完全再現可能。
        """
        from portfolio.decision_log import append_decision

        news_context = {
            "sentiment_score": "0.65",
            "confidence": "0.85",
            "summary": "AI 投資加速、決算良好",
            "key_themes": ["earnings beat", "AI investment"],
            "risk_signals": ["regulatory headwind"],
            "source_urls": [
                "https://example.com/aapl-q1",
                "https://example.com/aapl-ai",
            ],
            "fetched_at": "2026-05-09T14:30:00+00:00",
            "model_version": "claude-haiku-4-5-20251001",
            "lenses_applied": ["Buffett_Munger", "Burry"],
        }

        log_path = append_decision(
            log_dir=tmp_path,
            action="BUY",
            ticker="AAPL",
            shares=Decimal("10"),
            price_jpy=Decimal("25000"),
            rationale="Magic Formula スコア + ニュース強気センチメント",
            trigger={"skill": "magic-formula-screener"},
            news_context=news_context,
        )

        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert record["news_context"]["sentiment_score"] == "0.65"
        assert "Buffett_Munger" in record["news_context"]["lenses_applied"]
        assert record["news_context"]["model_version"] == (
            "claude-haiku-4-5-20251001"
        )


@pytest.mark.unit
class TestBuildNewsContextFromSentiment:
    """SentimentResult + ニュース DataFrame → news_context dict 変換ヘルパー。"""

    def test_SentimentResult_news_df_からnews_context構築(self) -> None:
        from datetime import datetime as DT
        from datetime import timezone as TZ
        from decimal import Decimal as D

        import pandas as pd

        from analysis.sentiment import SentimentMetadata, SentimentResult
        from portfolio.decision_log import build_news_context_from_sentiment

        result = SentimentResult(
            sentiment_score=D("0.65"),
            confidence=D("0.85"),
            key_themes=("AI", "earnings"),
            risk_signals=("regulation",),
            summary="強気",
            metadata=SentimentMetadata(
                model="claude-haiku-4-5",
                model_version="claude-haiku-4-5-20251001",
                calculation_method="sentiment_v1",
                input_news_count=2,
                input_period_start=None,
                input_period_end=None,
                calculated_at=DT.now(TZ.utc),
                academic_source="Tetlock 2007",
                code_commit=None,
            ),
        )
        news_df = pd.DataFrame(
            [
                {"url": "https://a"},
                {"url": "https://b"},
            ]
        )

        ctx = build_news_context_from_sentiment(
            result, news_df, lenses_applied=("Buffett_Munger",)
        )

        assert ctx["sentiment_score"] == "0.65"
        assert ctx["confidence"] == "0.85"
        assert ctx["summary"] == "強気"
        assert ctx["source_urls"] == ["https://a", "https://b"]
        assert ctx["lenses_applied"] == ["Buffett_Munger"]
        assert ctx["model_version"] == "claude-haiku-4-5-20251001"


@pytest.mark.unit
class TestReadDecisions:
    """過去の売買判断を読み出し（再現性検証用）。"""

    def test_月別ログ読み込み(self, tmp_path: Path) -> None:
        """指定月の JSONL を全行読んで dict のリストで返す。"""
        from portfolio.decision_log import append_decision, read_decisions

        append_decision(
            log_dir=tmp_path,
            action="BUY",
            ticker="A",
            shares=Decimal("1"),
            price_jpy=Decimal("100"),
            rationale="r1",
        )
        append_decision(
            log_dir=tmp_path,
            action="BUY",
            ticker="B",
            shares=Decimal("2"),
            price_jpy=Decimal("200"),
            rationale="r2",
        )

        yyyymm = datetime.now(timezone.utc).strftime("%Y-%m")
        records = read_decisions(log_dir=tmp_path, year_month=yyyymm)

        assert len(records) == 2
        assert records[0]["ticker"] == "A"
        assert records[1]["ticker"] == "B"

    def test_存在しない月は空リスト(self, tmp_path: Path) -> None:
        from portfolio.decision_log import read_decisions

        records = read_decisions(log_dir=tmp_path, year_month="2020-01")

        assert records == []
