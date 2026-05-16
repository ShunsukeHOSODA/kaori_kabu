"""anthropic SDK クライアント の Protocol 型定義 (Phase 6.3 §4.13 派生)。

handoff §4.13 の解消: Phase 6.2 で ``import anthropic`` を module top に移動した
foundation の上に、``anthropic.Anthropic`` を Protocol 化することで、テスト時の
``unittest.mock.MagicMock`` も duck-typing で受け入れる DI 型を提供する。

設計方針:
    - ``Protocol`` で structural typing を採用 (PEP 544)。``MagicMock`` は
      自動的に任意の属性アクセスを許容するため duck-type で satisfy する。
    - kaori_kabu で実際に使う 2 つの API (``messages.create()`` と
      ``models.list()``) のみを Protocol 化する。``client.completions`` 等の
      未使用 API は Protocol に含めない (over-spec を避ける)。
    - 返り値は ``Any`` を許容する。Anthropic SDK の response 型 (例:
      ``Message`` / ``SyncPage[ModelInfo]``) を構造的に書き写すコストが
      実益を上回るため、内部の ``response.content[0].text`` / ``response.usage``
      / ``model.id`` 等のアクセスは現状の duck-typing に委ねる。

利用例:
    >>> from src.analysis._anthropic_types import AnthropicLike
    >>>
    >>> def call_sonnet(*, client: AnthropicLike) -> str:
    ...     response = client.messages.create(
    ...         model="claude-sonnet-4-6",
    ...         max_tokens=100,
    ...         messages=[{"role": "user", "content": "hi"}],
    ...     )
    ...     return response.content[0].text

テスト時:
    >>> from unittest.mock import MagicMock
    >>> mock_client = MagicMock()  # AnthropicLike として自動 satisfy
    >>> mock_client.messages.create.return_value = ...
"""

from __future__ import annotations

from typing import Any, Protocol


class AnthropicMessagesResource(Protocol):
    """``anthropic.Anthropic.messages`` 互換の Protocol。

    ``create()`` のみを必須 API として宣言する。本プロジェクトでは
    streaming API (``stream()``) を使わないため Protocol に含めない。
    """

    def create(self, **kwargs: Any) -> Any:
        """Sonnet / Haiku への message 送信。返り値は SDK の ``Message`` 互換。

        Args:
            **kwargs: ``model``, ``max_tokens``, ``system``, ``messages`` 等。
                SDK のメソッドシグネチャをそのまま透過させる。

        Returns:
            ``response.content[0].text`` / ``response.usage.input_tokens`` 等で
            アクセスする SDK の ``Message`` インスタンス。
        """
        ...


class AnthropicModelsResource(Protocol):
    """``anthropic.Anthropic.models`` 互換の Protocol。

    ``list()`` のみを必須 API として宣言する。``retrieve()`` 等の単一
    モデル取得 API は ``resolve_sonnet_model_version`` で使用しないため
    Protocol に含めない。
    """

    def list(self, **kwargs: Any) -> Any:
        """利用可能モデル一覧の取得。返り値は SDK の ``SyncPage[ModelInfo]`` 互換。

        Args:
            **kwargs: ``limit`` 等の pagination パラメータ。

        Returns:
            iterable な ``model.id`` を持つオブジェクトのコレクション。
            ``resolve_sonnet_model_version`` は ``.data`` 属性で iterate する。
        """
        ...


class AnthropicLike(Protocol):
    """``anthropic.Anthropic`` 互換クライアントの Protocol (Phase 6.3 §4.13 派生)。

    本プロジェクトで使用する 2 つの API (``messages.create()`` と
    ``models.list()``) を持つ任意のオブジェクトを受け入れる構造的型。

    実装例:
        - ``anthropic.Anthropic`` (本物の SDK クライアント、production 経路)
        - ``unittest.mock.MagicMock`` (テスト用、自動 duck-type satisfaction)
        - 将来の代替 client (例: 自前 LLM gateway) も Protocol 互換なら DI 可能

    Note:
        ``Any`` 注釈に対する型安全性向上が目的。テスト 572 件で MagicMock
        を使った DI が確立されており、Protocol 化で mypy/pyright が
        引数型ミスを検出可能になる (handoff §4.13 解消)。
    """

    @property
    def messages(self) -> AnthropicMessagesResource:
        """``messages.create()`` への getter。"""
        ...

    @property
    def models(self) -> AnthropicModelsResource:
        """``models.list()`` への getter。"""
        ...
