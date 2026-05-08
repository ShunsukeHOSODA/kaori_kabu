"""kaori_kabu CLI エントリーポイント。

`kabu` コマンドで利用可能（pyproject.toml の [project.scripts] 経由）。
"""

from __future__ import annotations

import sys

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="kabu")
def cli() -> None:
    """かおりんの株運用 CLI。"""


@cli.command()
def dashboard() -> None:
    """Streamlit ダッシュボードを起動する。"""
    import subprocess

    click.echo("🚀 Streamlit ダッシュボード起動中...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "src/dashboard/app.py"],
        check=False,
    )


@cli.command()
def status() -> None:
    """API キー設定状況を確認する。"""
    from src.config.settings import settings

    click.echo("📋 API 設定状況:")
    api_status = {
        "EODHD": bool(settings.eodhd_api_key),
        "J-Quants": bool(settings.jquants_refresh_token),
        "SEC EDGAR": bool(settings.sec_edgar_user_agent),
        "FRED": bool(settings.fred_api_key),
    }
    for name, configured in api_status.items():
        icon = "✅" if configured else "❌"
        click.echo(f"  {icon} {name}")


def main() -> None:
    """エントリーポイント。"""
    cli()


if __name__ == "__main__":
    main()
