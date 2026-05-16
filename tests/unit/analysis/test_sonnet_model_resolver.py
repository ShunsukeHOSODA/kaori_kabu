"""Phase 5.5.3: Sonnet ``model_version`` 動的解決のユニットテスト。

handoff-session-6 §5.7 / C-L-1 持ち越し課題の実装検証。
mock anthropic_client で ``models.list()`` の戻り値を作って 6 ケースを検証する。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.analysis._sonnet_model_resolver import (
    DEFAULT_PREFIX,
    resolve_sonnet_model_version,
)


def _make_model(model_id: str) -> SimpleNamespace:
    """anthropic.types.ModelInfo もどき (id 属性のみ)。"""
    return SimpleNamespace(id=model_id)


def _make_client(model_ids: list[str]) -> MagicMock:
    """anthropic.Anthropic クライアントの mock。"""
    client = MagicMock()
    client.models.list.return_value = SimpleNamespace(
        data=[_make_model(mid) for mid in model_ids]
    )
    return client


@pytest.mark.unit
class TestResolveSonnetModelVersion:
    """``resolve_sonnet_model_version`` の挙動を 6 ケースで検証する。"""

    def test_client_none_returns_prefix(self) -> None:
        """anthropic_client=None のとき prefix をそのまま返す。"""
        result = resolve_sonnet_model_version(None)
        assert result == DEFAULT_PREFIX

    def test_client_none_returns_fallback_when_provided(self) -> None:
        """anthropic_client=None + fallback 明示で fallback を返す。"""
        result = resolve_sonnet_model_version(None, fallback="fixed-id")
        assert result == "fixed-id"

    def test_returns_latest_dated_snapshot(self) -> None:
        """prefix にマッチする 3 つの ID から最新 (降順 sort 1 番目) を返す。"""
        client = _make_client(
            [
                "claude-sonnet-4-6-20250514",
                "claude-sonnet-4-6-20250301",
                "claude-sonnet-4-6-20250101",
                "claude-haiku-4-5-20251001",  # prefix 不一致は無視
                "claude-opus-4-5-20251101",  # prefix 不一致は無視
            ]
        )
        result = resolve_sonnet_model_version(client)
        assert result == "claude-sonnet-4-6-20250514"
        client.models.list.assert_called_once()

    def test_no_dated_snapshot_returns_fallback(self) -> None:
        """prefix にマッチする日付付きが無いとき fallback を返す。"""
        client = _make_client(
            [
                "claude-sonnet-4-6",  # 日付なし (prefix + "-" で始まらない)
                "claude-haiku-4-5-20251001",  # prefix 不一致
            ]
        )
        result = resolve_sonnet_model_version(client, fallback="fallback-id")
        assert result == "fallback-id"

    def test_api_error_returns_fallback(self) -> None:
        """anthropic.models.list() が例外を投げると fallback を返す。"""
        client = MagicMock()
        client.models.list.side_effect = RuntimeError("API down")
        result = resolve_sonnet_model_version(client, fallback="settings-value")
        assert result == "settings-value"

    def test_custom_prefix_filters_correctly(self) -> None:
        """prefix を変えると別モデル系列の最新を返す。"""
        client = _make_client(
            [
                "claude-sonnet-4-6-20250514",
                "claude-opus-4-7-20260101",
                "claude-opus-4-7-20251101",
            ]
        )
        result = resolve_sonnet_model_version(client, prefix="claude-opus-4-7")
        assert result == "claude-opus-4-7-20260101"


@pytest.mark.unit
def test_default_prefix_value() -> None:
    """DEFAULT_PREFIX 定数が Sonnet 4.6 系を指している。"""
    assert DEFAULT_PREFIX == "claude-sonnet-4-6"
