"""売買判断ログ（Decision Log、append-only JSONL）。

CLAUDE.md §9.5 / §9.8.3 に準拠:
    - append-only 構造で過去の判断を改ざん不能に保つ
    - Provenance 込み（trigger / code_commit）で「なぜ買ったか」を完全再現
    - 月別ファイル（``{log_dir}/{YYYY-MM}.jsonl``）でローテーション

JSONL 1 行のスキーマ:
    {
        "timestamp": "2026-05-09T14:30:00+00:00",
        "action": "BUY" | "SELL" | "HOLD",
        "ticker": "AAPL",
        "shares": "10",
        "price_jpy": "25000",
        "rationale": "Magic Formula スコア 87/100",
        "trigger": {"skill": "magic-formula-screener", ...} | null,
        "stop_loss_atr_jpy": "22500" | null,
        "code_commit": "edabbe1" | null
    }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


def append_decision(
    *,
    log_dir: Path,
    action: str,
    ticker: str,
    shares: Decimal,
    price_jpy: Decimal,
    rationale: str,
    trigger: dict[str, Any] | None = None,
    stop_loss_atr_jpy: Decimal | None = None,
    code_commit: str | None = None,
) -> Path:
    """売買判断を JSONL に 1 行追記（append-only）。

    ファイル名は実行時刻の年月で決定（``{log_dir}/{YYYY-MM}.jsonl``）。
    既存があれば追記、なければ作成（親ディレクトリも自動作成）。

    Args:
        log_dir: ログ保存ルート
        action: ``BUY`` / ``SELL`` / ``HOLD``
        ticker: ティッカーシンボル
        shares: 株数（Decimal、文字列で保存される）
        price_jpy: 取引単価 JPY（Decimal、文字列で保存される）
        rationale: 判断根拠（自由記述）
        trigger: 判断のきっかけ（スキル名 / スコア等）
        stop_loss_atr_jpy: ATR トレーリングストップ価格（JPY）
        code_commit: 計算時の git commit short hash

    Returns:
        書き込み先のパス。
    """
    now = datetime.now(timezone.utc)
    log_path = log_dir / f"{now.strftime('%Y-%m')}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "action": action,
        "ticker": ticker,
        "shares": str(shares),
        "price_jpy": str(price_jpy),
        "rationale": rationale,
        "trigger": trigger,
        "stop_loss_atr_jpy": (
            str(stop_loss_atr_jpy) if stop_loss_atr_jpy is not None else None
        ),
        "code_commit": code_commit,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return log_path


def read_decisions(
    *, log_dir: Path, year_month: str
) -> list[dict[str, Any]]:
    """指定月の Decision Log を読み込み（存在しなければ空リスト）。

    Args:
        log_dir: ログディレクトリ
        year_month: ``YYYY-MM`` 形式（例 ``2026-05``）

    Returns:
        各行を dict にパースしたリスト（追記順）。
    """
    log_path = log_dir / f"{year_month}.jsonl"
    if not log_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records
