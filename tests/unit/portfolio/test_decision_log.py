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
        """trigger / stop_loss / code_commit を省略しても動く。"""
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
