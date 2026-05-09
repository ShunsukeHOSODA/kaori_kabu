"""Provenance ヘルパー（CLAUDE.md §9.8）。

複数モジュール（``regime.py`` / ``risk_metrics.py`` / ``atr_alert_logger`` 統合先 view）
で共通に必要な provenance 取得ロジックを集約する。

注:
    既存の ``regime.py::_get_current_git_commit`` /
    ``risk_metrics.py::_get_current_git_commit`` は後方互換のため残置。
    新規モジュールは本ヘルパーを使う方針（重複実装の増殖を止める）。
    既存 2 ファイルの統合は別 PR で対応。
"""

from __future__ import annotations

import subprocess


def get_current_git_commit() -> str | None:
    """現在の git commit short hash。失敗時は ``None``。

    タイムアウト 2 秒、シェル経由なし、固定引数のみで安全。

    Returns:
        ``git rev-parse --short HEAD`` の出力。失敗時 ``None``。
    """
    try:
        completed = subprocess.run(  # noqa: S603, S607 — 固定引数のみ、シェル経由なし
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None
