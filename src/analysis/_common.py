"""src/analysis 配下の共通ヘルパー（純粋関数のみ）。

CLAUDE.md §9.8 / handoff-session-3.md §5.4 で計画された Phase 6
リファクタの一環。``ranking_judge.py`` / ``sentiment.py`` で重複していた
``_extract_json`` の単一真実源を提供し、drift を防ぐ。

Provenance ヘルパー（git commit 取得など）は :mod:`analysis._provenance`
側に既に集約済み。本モジュールは LLM 応答パース等の共通ロジックに限定する。
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str, *, context: str) -> dict[str, Any]:
    """LLM 応答テキストから JSON dict を抽出する。

    抽出順序:
        1. ``` ```json ... ``` ``` または ``` ``` ... ``` ``` のコードフェンス
        2. 最初の ``{`` から最後の ``}`` までを切り出して ``json.loads``

    Args:
        text: LLM が返した生テキスト。
        context: 失敗時のエラーメッセージに埋め込む呼び出し元識別子
            （例: ``"ranking judge response"`` / ``"sentiment analysis response"``）。
            UI 表示や Decision Log 解析のため呼び出し元の明示を必須化。

    Returns:
        パース済み JSON dict。

    Raises:
        ValueError: JSON ブロックが見つからなかった場合
            （メッセージは ``f"JSON not found in {context}"``）。
        json.JSONDecodeError: JSON 構文不正の場合（``json.loads`` から伝播）。
    """
    fence = _FENCE_PATTERN.search(text)
    if fence:
        return json.loads(fence.group(1))  # type: ignore[no-any-return]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"JSON not found in {context}")
    return json.loads(text[start : end + 1])  # type: ignore[no-any-return]
