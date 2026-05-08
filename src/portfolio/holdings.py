"""保有銘柄管理（Holding / Portfolio）。

CLAUDE.md §4 / §9.1 / §9.6 に準拠:
    - 金額は Decimal 型
    - 日付は date オブジェクト（文字列で持ち回さない）
    - 口座種別タグ（NISA / 特定 / 旧NISA）必須 — after-tax リターン分離の前提
    - immutable データ構造（frozen dataclass）

CSV フォーマット (``data/holdings/portfolio.csv``):
    ticker,exchange,shares,avg_cost_jpy,purchased_at,account_type
    AAPL,US,10,25000,2025-01-15,NISA
    7203,TO,100,2800,2024-12-01,特定
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Final

CSV_HEADERS: Final[list[str]] = [
    "ticker",
    "exchange",
    "shares",
    "avg_cost_jpy",
    "purchased_at",
    "account_type",
]


@dataclass(frozen=True)
class Holding:
    """1 銘柄の保有情報。

    Attributes:
        ticker: ティッカーシンボル（例: ``AAPL``、``7203``）
        exchange: 取引所（例: ``US``、``TO`` で東証）
        shares: 保有株数
        avg_cost_jpy: 取得平均単価（JPY）
        purchased_at: 取得日（最後の購入日 or 加重平均上の起点）
        account_type: 口座種別（``NISA`` / ``特定`` / ``旧NISA``）
    """

    ticker: str
    exchange: str
    shares: Decimal
    avg_cost_jpy: Decimal
    purchased_at: date
    account_type: str


@dataclass(frozen=True)
class Portfolio:
    """保有銘柄の集合。

    immutable で、追加/削除は新しい :class:`Portfolio` インスタンスを返す。
    """

    holdings: tuple[Holding, ...]

    def total_cost_jpy(self) -> Decimal:
        """全保有銘柄の合計取得コスト（JPY）。"""
        return sum(
            (h.shares * h.avg_cost_jpy for h in self.holdings),
            Decimal("0"),
        )

    def by_ticker(self, ticker: str) -> Holding | None:
        """ティッカーで銘柄を検索（存在しなければ None）。"""
        for h in self.holdings:
            if h.ticker == ticker:
                return h
        return None

    def add(self, holding: Holding) -> Portfolio:
        """銘柄を追加した新しい :class:`Portfolio` を返す。元は変更しない。"""
        return replace(self, holdings=self.holdings + (holding,))

    @classmethod
    def from_csv(cls, path: Path) -> Portfolio:
        """CSV ファイルから :class:`Portfolio` を読み込む。

        ファイルが存在しない場合は空 :class:`Portfolio` を返す（初回起動対応）。
        """
        if not path.exists():
            return cls(holdings=())

        holdings: list[Holding] = []
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                holdings.append(
                    Holding(
                        ticker=row["ticker"],
                        exchange=row["exchange"],
                        shares=Decimal(row["shares"]),
                        avg_cost_jpy=Decimal(row["avg_cost_jpy"]),
                        purchased_at=date.fromisoformat(row["purchased_at"]),
                        account_type=row["account_type"],
                    )
                )
        return cls(holdings=tuple(holdings))

    def to_csv(self, path: Path) -> None:
        """CSV ファイルに保存。親ディレクトリは自動作成。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for h in self.holdings:
                writer.writerow(
                    {
                        "ticker": h.ticker,
                        "exchange": h.exchange,
                        "shares": str(h.shares),
                        "avg_cost_jpy": str(h.avg_cost_jpy),
                        "purchased_at": h.purchased_at.isoformat(),
                        "account_type": h.account_type,
                    }
                )
