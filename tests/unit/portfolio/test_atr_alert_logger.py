"""ATR alert → Decision Log ブリッジの単体テスト。

CLAUDE.md §9.5 / §9.8.3 準拠:
    - ATR breach/near 抵触時に decision-log JSONL に自動追記
    - 月内 (ticker, status) 初回のみ記録（重複防止）
    - safe は記録対象外
    - USD は usdjpy_rate で JPY 換算
    - trigger.skill = "atr-trailing-stop"、metadata.alert_status で区別
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from dashboard.widgets.atr_alert import AtrAlert
from portfolio.holdings import Holding


def _make_alert(
    *,
    ticker: str = "AAPL",
    current: str = "280",
    stop: str = "277",
    status: str = "breach",
    currency: str = "USD",
) -> AtrAlert:
    return AtrAlert(
        ticker=ticker,
        current_price=Decimal(current),
        stop_price=Decimal(stop),
        status=status,  # type: ignore[arg-type]
        reason_lines=(),
        currency=currency,
    )


def _make_holding(
    *,
    ticker: str = "AAPL",
    exchange: str = "US",
    shares: str = "10",
) -> Holding:
    return Holding(
        ticker=ticker,
        exchange=exchange,
        shares=Decimal(shares),
        avg_cost_jpy=Decimal("25000"),
        purchased_at=date(2025, 1, 15),
        account_type="NISA",
    )


def _seed_existing_atr_record(
    *,
    log_dir: Path,
    ticker: str = "AAPL",
    alert_status: str = "breach",
    skill: str = "atr-trailing-stop",
) -> None:
    """既存 ATR レコードを 1 行 seed（実時刻の月のファイルに書く）。"""
    from portfolio.decision_log import append_decision

    log_dir.mkdir(parents=True, exist_ok=True)
    append_decision(
        log_dir=log_dir,
        action="HOLD",
        ticker=ticker,
        shares=Decimal("10"),
        price_jpy=Decimal("44000"),
        rationale="seed",
        trigger={
            "skill": skill,
            "metadata": {"alert_status": alert_status},
        },
    )


@pytest.mark.unit
class TestShouldLogAlert:
    """should_log_alert の純判定。"""

    def test_ログファイル無しなら_True(self, tmp_path: Path) -> None:
        from portfolio.atr_alert_logger import should_log_alert

        assert should_log_alert(
            alert=_make_alert(status="breach"),
            log_dir=tmp_path,
            year_month="2026-05",
        )

    def test_月内_同_status_既存なら_False(self, tmp_path: Path) -> None:
        """同じ月に同じ ticker × 同じ status の ATR レコードがあれば skip。"""
        from portfolio.atr_alert_logger import should_log_alert

        yyyymm = datetime.now(timezone.utc).strftime("%Y-%m")
        _seed_existing_atr_record(
            log_dir=tmp_path,
            ticker="AAPL",
            alert_status="breach",
        )

        assert not should_log_alert(
            alert=_make_alert(ticker="AAPL", status="breach"),
            log_dir=tmp_path,
            year_month=yyyymm,
        )

    def test_月内_別_status_は_True_状態遷移(self, tmp_path: Path) -> None:
        """既存が breach、今回が near なら状態遷移として記録対象。"""
        from portfolio.atr_alert_logger import should_log_alert

        yyyymm = datetime.now(timezone.utc).strftime("%Y-%m")
        _seed_existing_atr_record(
            log_dir=tmp_path,
            ticker="AAPL",
            alert_status="breach",
        )

        assert should_log_alert(
            alert=_make_alert(ticker="AAPL", status="near"),
            log_dir=tmp_path,
            year_month=yyyymm,
        )

    def test_別月の同_status_は_True_月跨ぎ(self, tmp_path: Path) -> None:
        """別月のログは検査対象外。今月分ファイルが無ければ True。"""
        from portfolio.atr_alert_logger import should_log_alert

        # seed は 2025-12 月、検査対象は 2026-01 月（別ファイル）
        # year_month を未来月にして、ファイル不存在パスをカバー
        # （seed は実時刻の月に作られるが、ここでは別月を渡すので無関係）
        assert should_log_alert(
            alert=_make_alert(ticker="AAPL", status="breach"),
            log_dir=tmp_path,
            year_month="2030-01",
        )

    def test_他_skill_の既存レコードは無視(self, tmp_path: Path) -> None:
        """trigger.skill が atr-trailing-stop 以外なら重複検出に含めない。"""
        from portfolio.atr_alert_logger import should_log_alert

        yyyymm = datetime.now(timezone.utc).strftime("%Y-%m")
        _seed_existing_atr_record(
            log_dir=tmp_path,
            ticker="AAPL",
            alert_status="breach",
            skill="magic-formula-screener",  # 別スキル
        )

        assert should_log_alert(
            alert=_make_alert(ticker="AAPL", status="breach"),
            log_dir=tmp_path,
            year_month=yyyymm,
        )

    def test_safe_は記録対象外で_False(self, tmp_path: Path) -> None:
        """status='safe' は意味あるイベントではないので常に False。"""
        from portfolio.atr_alert_logger import should_log_alert

        assert not should_log_alert(
            alert=_make_alert(status="safe"),
            log_dir=tmp_path,
            year_month="2026-05",
        )


@pytest.mark.unit
class TestLogAtrAlert:
    """log_atr_alert の統合動作。"""

    def test_breach_JPY_は_換算なしで_JSONL_に_1行追加(
        self, tmp_path: Path
    ) -> None:
        """JPY 通貨の breach は usdjpy 換算せず price_jpy にそのまま入る。"""
        from portfolio.atr_alert_logger import log_atr_alert

        result = log_atr_alert(
            alert=_make_alert(
                ticker="7203",
                current="2900",
                stop="2850",
                status="breach",
                currency="JPY",
            ),
            holding=_make_holding(ticker="7203", exchange="TO", shares="100"),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="9bb59d8",
        )

        assert result is not None
        assert result.exists()
        record = json.loads(result.read_text(encoding="utf-8").strip())
        assert record["action"] == "HOLD"
        assert record["ticker"] == "7203"
        assert record["shares"] == "100"
        # JPY はそのまま
        assert record["price_jpy"] == "2900"
        assert record["stop_loss_atr_jpy"] == "2850"

    def test_breach_USD_は_usdjpy_で換算して_price_jpy(
        self, tmp_path: Path
    ) -> None:
        """USD 通貨は usdjpy_rate で換算後に price_jpy / stop_loss_atr_jpy に入る。"""
        from portfolio.atr_alert_logger import log_atr_alert

        result = log_atr_alert(
            alert=_make_alert(
                ticker="AAPL",
                current="280",
                stop="277",
                status="breach",
                currency="USD",
            ),
            holding=_make_holding(ticker="AAPL", exchange="US", shares="10"),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="9bb59d8",
        )

        assert result is not None
        record = json.loads(result.read_text(encoding="utf-8").strip())
        # 280 * 158 = 44240
        assert record["price_jpy"] == "44240"
        # 277 * 158 = 43766
        assert record["stop_loss_atr_jpy"] == "43766"

    def test_trigger_metadata_完全(self, tmp_path: Path) -> None:
        """trigger.metadata に alert_status / atr_period / 原通貨情報が揃う。"""
        from portfolio.atr_alert_logger import log_atr_alert

        result = log_atr_alert(
            alert=_make_alert(
                ticker="AAPL",
                current="280",
                stop="277",
                status="near",
                currency="USD",
            ),
            holding=_make_holding(ticker="AAPL", exchange="US"),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="9bb59d8",
            atr_period=14,
            atr_multiplier=Decimal("2.5"),
            lookback=20,
        )

        assert result is not None
        record = json.loads(result.read_text(encoding="utf-8").strip())
        trig = record["trigger"]
        assert trig["skill"] == "atr-trailing-stop"
        meta = trig["metadata"]
        assert meta["alert_status"] == "near"
        assert meta["atr_period"] == 14
        assert meta["atr_multiplier"] == "2.5"
        assert meta["lookback"] == 20
        assert meta["stop_price_original"] == "277"
        assert meta["current_price_original"] == "280"
        assert meta["currency_original"] == "USD"
        assert meta["usdjpy_rate_applied"] == "158"
        # rationale に "売却検討" を含む（規律ベース）
        assert "売却検討" in record["rationale"]
        assert "接近" in record["rationale"] or "抵触" in record["rationale"]

    def test_重複時_None_を返し_JSONL_は変わらない(
        self, tmp_path: Path
    ) -> None:
        """同月に既存 (ticker, status) があれば None、ファイルも増えない。"""
        from portfolio.atr_alert_logger import log_atr_alert

        # 1 回目
        first = log_atr_alert(
            alert=_make_alert(ticker="AAPL", status="breach"),
            holding=_make_holding(ticker="AAPL"),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="abc123",
        )
        assert first is not None
        first_size = first.stat().st_size

        # 2 回目（同 ticker × 同 status）
        second = log_atr_alert(
            alert=_make_alert(ticker="AAPL", status="breach"),
            holding=_make_holding(ticker="AAPL"),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="abc123",
        )

        assert second is None
        # ファイルサイズが変わらない = 追記されていない
        assert first.stat().st_size == first_size

    def test_safe_は_None_を返し_JSONL作成すらしない(
        self, tmp_path: Path
    ) -> None:
        """status=safe は記録対象外、ファイルも作らない。"""
        from portfolio.atr_alert_logger import log_atr_alert

        result = log_atr_alert(
            alert=_make_alert(status="safe"),
            holding=_make_holding(),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="abc123",
        )

        assert result is None
        # tmp_path 配下に jsonl ファイルが無い
        assert not list(tmp_path.glob("*.jsonl"))

    def test_code_commit_は_top_level_のみ_伝播(self, tmp_path: Path) -> None:
        """code_commit はレコード top-level の code_commit のみに入り、
        trigger.metadata には漏れない（責務分離）。"""
        from portfolio.atr_alert_logger import log_atr_alert

        result = log_atr_alert(
            alert=_make_alert(status="breach"),
            holding=_make_holding(),
            log_dir=tmp_path,
            usdjpy_rate=Decimal("158"),
            code_commit="9bb59d8",
        )

        assert result is not None
        record = json.loads(result.read_text(encoding="utf-8").strip())
        assert record["code_commit"] == "9bb59d8"
        assert "code_commit" not in record["trigger"]["metadata"]
