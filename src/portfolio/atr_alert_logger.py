"""ATR alert → Decision Log ブリッジ。

CLAUDE.md §9.5 / §9.8.3 準拠:
    - ATR breach/near 抵触時に decision-log JSONL に自動追記
    - 月内 (ticker, status) 初回のみ記録（重複防止）
    - safe は記録対象外（イベントとして意味がない）
    - USD 通貨は usdjpy_rate で JPY 換算（原通貨情報は trigger.metadata に保存）
    - 規律ベース表現: action="HOLD" + rationale で「売却検討」を明示。
      AI が自動売買したと誤読されないため SELL は使わない。

スキーマ詳細は ``.steering/20260509-atr-decision-log-bridge/design.md`` 参照。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from .decision_log import append_decision, read_decisions

if TYPE_CHECKING:
    from dashboard.widgets.atr_alert import AtrAlert
    from portfolio.holdings import Holding


_SKILL_NAME: Final[str] = "atr-trailing-stop"
"""trigger.skill の固定値。重複検出と集計の両方で使う。"""

_LOG_TARGET_STATUSES: Final[frozenset[str]] = frozenset({"breach", "near"})
"""記録対象の status。``safe`` は意味あるイベントではないので除外。"""

_STATUS_LABEL: Final[dict[str, str]] = {
    "breach": "抵触",
    "near": "接近",
}


def should_log_alert(
    *,
    alert: AtrAlert,
    log_dir: Path,
    year_month: str,
) -> bool:
    """ATR alert を Decision Log に記録すべきかを判定。

    Returns:
        True 条件:
            - ``alert.status`` が ``'breach'`` または ``'near'``
            - 指定月に同 ``(ticker, alert_status)`` の
              ``atr-trailing-stop`` 既存レコードが無い
        その他は False。

    Args:
        alert: ATR 評価結果
        log_dir: Decision Log ディレクトリ（月別 JSONL を含む）
        year_month: ``YYYY-MM`` 形式（重複チェック対象月）
    """
    if alert.status not in _LOG_TARGET_STATUSES:
        return False

    existing = read_decisions(log_dir=log_dir, year_month=year_month)
    for record in existing:
        trigger = record.get("trigger") or {}
        if trigger.get("skill") != _SKILL_NAME:
            continue
        if record.get("ticker") != alert.ticker:
            continue
        metadata = trigger.get("metadata") or {}
        if metadata.get("alert_status") == alert.status:
            return False

    return True


def log_atr_alert(
    *,
    alert: AtrAlert,
    holding: Holding,
    log_dir: Path,
    usdjpy_rate: Decimal,
    code_commit: str | None = None,
    atr_period: int = 14,
    atr_multiplier: Decimal = Decimal("2.5"),
    lookback: int = 20,
) -> Path | None:
    """ATR alert を Decision Log JSONL に 1 行追記（重複防止つき）。

    USD 通貨は ``usdjpy_rate`` で JPY 換算して ``price_jpy`` /
    ``stop_loss_atr_jpy`` に格納。原通貨の数値は
    ``trigger.metadata.{stop,current}_price_original`` に残す。

    Args:
        alert: ATR 評価結果（``status`` が ``safe`` の場合は何もしない）
        holding: 保有銘柄情報（``shares`` を ``shares`` フィールドに転記）
        log_dir: Decision Log ディレクトリ
        usdjpy_rate: USD→JPY 換算レート（USD 通貨時のみ使用）
        code_commit: 計算時の git commit short hash（top-level に保存）
        atr_period: ATR 計算期間（trigger.metadata に保存）
        atr_multiplier: ATR 倍数（trigger.metadata に保存）
        lookback: 最高値ルックバック期間（trigger.metadata に保存）

    Returns:
        書き込み先パス。``safe`` または重複で skip 時は ``None``。
    """
    now = datetime.now(timezone.utc)
    year_month = now.strftime("%Y-%m")

    if not should_log_alert(
        alert=alert, log_dir=log_dir, year_month=year_month
    ):
        return None

    if alert.currency == "USD":
        price_jpy = alert.current_price * usdjpy_rate
        stop_loss_atr_jpy = alert.stop_price * usdjpy_rate
        usdjpy_applied: str | None = str(usdjpy_rate)
    else:
        price_jpy = alert.current_price
        stop_loss_atr_jpy = alert.stop_price
        usdjpy_applied = None

    status_label = _STATUS_LABEL.get(alert.status, alert.status)
    rationale = (
        f"ATR トレーリングストップ条件{status_label}"
        f"（基準 {alert.currency} {alert.stop_price}、"
        f"現在 {alert.currency} {alert.current_price}）"
        f" → 売却検討"
    )

    trigger: dict[str, Any] = {
        "skill": _SKILL_NAME,
        "metadata": {
            "alert_status": alert.status,
            "atr_period": atr_period,
            "atr_multiplier": str(atr_multiplier),
            "lookback": lookback,
            "stop_price_original": str(alert.stop_price),
            "current_price_original": str(alert.current_price),
            "currency_original": alert.currency,
            "usdjpy_rate_applied": usdjpy_applied,
        },
    }

    return append_decision(
        log_dir=log_dir,
        action="HOLD",
        ticker=alert.ticker,
        shares=holding.shares,
        price_jpy=price_jpy,
        rationale=rationale,
        trigger=trigger,
        stop_loss_atr_jpy=stop_loss_atr_jpy,
        code_commit=code_commit,
    )
