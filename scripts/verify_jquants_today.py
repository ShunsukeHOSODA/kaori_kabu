"""J-Quants Light の「当日データ取得可否」検証スクリプト（§4.3、handoff-phase4.md）。

公式ページの記載「Light 以上はリアルタイム/当日対応」を実機で確認。
CLAUDE.md §5 / handoff の「Light = 12 週遅延」前提が崩れる可能性があるため。

実行:
    .venv/bin/python scripts/verify_jquants_today.py

結果の解釈:
    - 当日データ (latest_date == today) が返る → 90 日遅延ロジック撤回可能
    - 前日まで → 大引け前の実行 or Light の挙動として「翌営業日反映」
    - エラー（401/403） → API key 未設定 or プラン制限
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.config.settings import settings  # noqa: E402
from src.data.cache import ParquetCache  # noqa: E402
from src.data.jquants import (  # noqa: E402
    JQuantsAPIError,
    JQuantsAuthError,
    JQuantsClient,
    JQuantsConfigError,
)


def main() -> int:
    if not settings.jquants_api_key:
        print("❌ JQUANTS_API_KEY が未設定（.env を確認）")
        return 1

    today = date.today()
    # 過去 14 日でリクエスト → 直近の取得可能日を観測
    from_d = today - timedelta(days=14)

    cache = ParquetCache(base_dir=settings.cache_dir)
    client = JQuantsClient(api_key=settings.jquants_api_key, cache=cache)

    for ticker in ("7203", "6758"):
        print(f"\n=== {ticker} ===")
        print(f"リクエスト範囲: {from_d} → {today}")
        try:
            df = client.get_eod(ticker, from_date=from_d, to_date=today)
        except (JQuantsAPIError, JQuantsAuthError, JQuantsConfigError) as e:
            print(f"❌ API error: {type(e).__name__}: {e}")
            continue

        print(f"返却行数: {len(df)}")
        if df.empty:
            print("⚠️ 空 DF")
            continue

        if "Date" in df.columns:
            latest = df["Date"].max()
            print(f"最新日付: {latest}")
            print(f"今日からの遅延: {(today - latest.date()).days} 日")
        if "Close" in df.columns:
            print(f"最新終値: {df.iloc[-1].get('Close')}")
        print(f"attrs: source={df.attrs.get('source')}, "
              f"fetched_at={df.attrs.get('fetched_at')}, "
              f"cache_hit={df.attrs.get('cache_hit')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
