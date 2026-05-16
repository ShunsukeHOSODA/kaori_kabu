"""Composite Score テーブル → BUY 確定 → Decision Log 書き込みのロジック層テスト。

§4.2 #3 残課題（handoff-phase4.md §11.3）に対応。
02_screener.py の UI ロジックを切り出して pytest でカバー可能にする
（UI と独立してテスト可能、Streamlit ランタイム不要）。

CLAUDE.md §9.5 / §9.8.3 に準拠:
    - kelly_recommendation を自動付与（build_kelly_recommendation 経由）
    - trigger に screener metadata（preset / composite_score / sub_scores）
    - rationale を composite_score 込みで自動生成
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Factory fixtures (handoff §4.10: 5 箇所の BuyOrderRequest 重複構築を統一)
# ---------------------------------------------------------------------------


@pytest.fixture
def make_screener_trigger() -> Callable[..., Any]:
    """ScreenerTrigger 構築 factory。override する field のみ kwargs で指定可能。"""

    def _make(**overrides: Any) -> Any:
        from portfolio.buy_decision import ScreenerTrigger

        defaults: dict[str, Any] = {
            "skill": "composite-score-screener",
            "preset": "Buffett_型_暫定",
            "composite_score": Decimal("80"),
            "sub_scores": {"Q": Decimal("80")},
            "screener_run_at": "2026-05-11T10:00:00+00:00",
        }
        defaults.update(overrides)
        return ScreenerTrigger(**defaults)

    return _make


@pytest.fixture
def make_buy_request(
    make_screener_trigger: Callable[..., Any],
) -> Callable[..., Any]:
    """BuyOrderRequest 構築 factory。override する field のみ kwargs で指定可能。

    ``trigger`` を override しない場合は ``make_screener_trigger()`` のデフォルト
    ScreenerTrigger が埋まる。kelly_params / portfolio_value_jpy は全テスト共通の
    ``KellyParams(win_rate=0.6, win_loss_ratio=2.0)`` / ``Decimal("1000000")`` を採用。
    """

    def _make(**overrides: Any) -> Any:
        from portfolio.buy_decision import BuyOrderRequest
        from strategies.kelly import KellyParams

        defaults: dict[str, Any] = {
            "ticker": "AAPL",
            "shares": Decimal("1"),
            "price_jpy": Decimal("25000"),
            "trigger": make_screener_trigger(),
            "kelly_params": KellyParams(
                win_rate=Decimal("0.6"), win_loss_ratio=Decimal("2.0")
            ),
            "portfolio_value_jpy": Decimal("1000000"),
        }
        defaults.update(overrides)
        return BuyOrderRequest(**defaults)

    return _make


@pytest.mark.unit
class TestSubmitBuyOrder:
    """02_screener Composite Score テーブル → BUY → Decision Log。"""

    def test_kelly_recommendation_込みでJSONLを書く(
        self,
        tmp_path: Path,
        make_buy_request: Callable[..., Any],
        make_screener_trigger: Callable[..., Any],
    ) -> None:
        """BUY 注文を提出すると、Kelly 計算過程込みで JSONL に書き込まれる。

        Provenance §9.8.3: 「なぜこの数量を買ったか」を Kelly 計算過程込みで再現可能。
        """
        from portfolio.buy_decision import submit_buy_order

        request = make_buy_request(
            shares=Decimal("2"),
            trigger=make_screener_trigger(
                composite_score=Decimal("82.3"),
                sub_scores={"Q": Decimal("80"), "V": Decimal("75")},
            ),
            code_commit="abc1234",
        )

        log_path = submit_buy_order(request, log_dir=tmp_path)

        assert log_path.exists()
        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert record["action"] == "BUY"
        assert record["ticker"] == "AAPL"
        assert record["shares"] == "2"
        assert record["price_jpy"] == "25000"
        assert record["code_commit"] == "abc1234"

        # Kelly 推奨が自動付与されている（capped 5% × ¥1,000,000 = ¥50,000）
        assert record["kelly_recommendation"] is not None
        # build_kelly_recommendation は Decimal 演算 → 文字列化なので
        # "50000" / "50000.0" / "50000.00" 等の表現に揺れがあるため
        # Decimal で比較する
        assert Decimal(record["kelly_recommendation"]["recommended_size_jpy"]) == Decimal("50000")
        assert (
            record["kelly_recommendation"]["calculation_method"] == "half_kelly_v1"
        )
        assert record["kelly_recommendation"]["win_rate"] == "0.6"

    def test_trigger_に_screener_metadata_が含まれる(
        self,
        tmp_path: Path,
        make_buy_request: Callable[..., Any],
        make_screener_trigger: Callable[..., Any],
    ) -> None:
        """trigger に preset / composite_score / sub_scores / screener_run_at が
        全て含まれる（後で「なぜこのスコアで買ったか」を完全再現可能）。"""
        from portfolio.buy_decision import submit_buy_order

        request = make_buy_request(
            ticker="MSFT",
            price_jpy=Decimal("60000"),
            trigger=make_screener_trigger(
                preset="モメンタム型",
                composite_score=Decimal("79.1"),
                sub_scores={"Q": Decimal("78"), "M": Decimal("65")},
                screener_run_at="2026-05-11T11:00:00+00:00",
            ),
        )

        log_path = submit_buy_order(request, log_dir=tmp_path)

        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        trigger = record["trigger"]
        assert trigger["skill"] == "composite-score-screener"
        assert trigger["preset"] == "モメンタム型"
        assert trigger["composite_score"] == "79.1"
        assert trigger["sub_scores"]["Q"] == "78"
        assert trigger["sub_scores"]["M"] == "65"
        assert trigger["screener_run_at"] == "2026-05-11T11:00:00+00:00"

    def test_rationale_にcomposite_score_と追加根拠_が含まれる(
        self,
        tmp_path: Path,
        make_buy_request: Callable[..., Any],
        make_screener_trigger: Callable[..., Any],
    ) -> None:
        """rationale は Composite Score と preset を自動生成、ユーザー記述があれば追記。"""
        from portfolio.buy_decision import submit_buy_order

        request = make_buy_request(
            ticker="GOOGL",
            price_jpy=Decimal("30000"),
            trigger=make_screener_trigger(
                composite_score=Decimal("75.8"),
                screener_run_at="2026-05-11T12:00:00+00:00",
            ),
            additional_rationale="長期保有候補、決算良好",
        )

        log_path = submit_buy_order(request, log_dir=tmp_path)

        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        rationale = record["rationale"]
        assert "GOOGL" in rationale
        assert "75.8" in rationale
        assert "Buffett_型_暫定" in rationale
        assert "長期保有候補、決算良好" in rationale


@pytest.mark.unit
class TestSubmitBuyOrderClaudeRanking:
    """Phase 5.4.3: BuyOrderRequest.claude_ranking が Decision Log に記録される。

    Provenance §9.8.3: 「なぜこの銘柄を買ったか」を Claude 判定
    （ranking_score / counter_view / lens_views / kelly_multiplier 等）
    まで含めて完全再現可能。
    """

    def test_claude_ranking指定時にJSONLへ書き込まれる(
        self,
        tmp_path: Path,
        make_buy_request: Callable[..., Any],
        make_screener_trigger: Callable[..., Any],
    ) -> None:
        """claude_ranking dict が Decision Log の claude_ranking フィールド
        にそのまま書き込まれる。
        """
        from portfolio.buy_decision import submit_buy_order

        claude_rank_dict = {
            "ranking_score": 87,
            "recommendation_summary": "テスト用判定",
            "supporting_signals": ["ROC 高", "EY 高"],
            "risk_signals": ["セクター集中"],
            "counter_view": "Value Trap 可能性",
            "lens_views": {
                "Buffett_Munger": "質高、長期保有妥当",
                "Burry": "テールリスク低",
                "Lynch": "成長余地あり",
            },
            "confidence": "0.82",
            "confidence_adjusted": "0.78",
            "kelly_multiplier": "0.95",
            "fallback_reason": None,
            "metadata": {"model": "claude-sonnet-4-6"},
        }
        request = make_buy_request(
            shares=Decimal("10"),
            trigger=make_screener_trigger(
                composite_score=Decimal("82.5"),
                sub_scores={"Q": Decimal("90")},
                screener_run_at="2026-05-15T10:00:00+00:00",
            ),
            claude_ranking=claude_rank_dict,
        )
        log_path = submit_buy_order(request, log_dir=tmp_path)

        # 書き込まれた JSONL の最終行を読む
        with log_path.open("r", encoding="utf-8") as f:
            last_line = f.readlines()[-1]
        record = json.loads(last_line)

        assert record["claude_ranking"] is not None
        assert record["claude_ranking"]["ranking_score"] == 87
        assert (
            record["claude_ranking"]["lens_views"]["Burry"] == "テールリスク低"
        )

    def test_claude_ranking不指定時は後方互換でNone(
        self,
        tmp_path: Path,
        make_buy_request: Callable[..., Any],
        make_screener_trigger: Callable[..., Any],
    ) -> None:
        """claude_ranking 引数を省略しても既存 BuyOrderRequest 構築は成功し、
        JSONL の claude_ranking フィールドは ``None`` で書き込まれる。
        """
        from portfolio.buy_decision import submit_buy_order

        request = make_buy_request(
            ticker="MSFT",
            shares=Decimal("5"),
            price_jpy=Decimal("30000"),
            trigger=make_screener_trigger(
                composite_score=Decimal("75"),
                sub_scores={},
                screener_run_at="2026-05-15T10:00:00+00:00",
            ),
            portfolio_value_jpy=Decimal("500000"),
        )
        log_path = submit_buy_order(request, log_dir=tmp_path)

        with log_path.open("r", encoding="utf-8") as f:
            last_line = f.readlines()[-1]
        record = json.loads(last_line)

        assert record["claude_ranking"] is None
