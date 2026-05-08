"""pytest 共通設定（CLAUDE.md §9.2）。

統合テスト（``marker=slow`` / ``integration``）が ``.env`` の API キーを
参照できるよう、セッション開始時に ``python-dotenv`` で読み込む。
``pydantic-settings`` の :class:`Settings` 経由ではなくテスト側が
``os.environ`` から直接読む場合に必要。
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
