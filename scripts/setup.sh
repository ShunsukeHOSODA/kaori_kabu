#!/usr/bin/env bash
# kaori_kabu セットアップスクリプト
# 使い方: bash scripts/setup.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "🚀 kaori_kabu セットアップ開始"
echo "  プロジェクト: $PROJECT_DIR"
echo

# 1. uv インストール確認
if ! command -v uv &>/dev/null; then
    echo "📦 uv 未インストール。インストールします..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "✅ uv インストール完了"
else
    echo "✅ uv インストール済み: $(uv --version)"
fi
echo

# 2. Python 3.12 取得（uv が自動取得）
echo "🐍 Python 3.12 を確認・取得します..."
uv python install 3.12
echo "✅ Python 3.12 準備完了"
echo

# 3. 仮想環境作成
if [[ ! -d ".venv" ]]; then
    echo "🌱 .venv 仮想環境作成中..."
    uv venv --python 3.12
    echo "✅ 仮想環境作成完了"
else
    echo "✅ 仮想環境 (.venv) は既に存在"
fi
echo

# 4. 依存インストール
echo "📚 依存関係をインストール中（数分かかります）..."
uv sync --extra dev
echo "✅ 依存インストール完了"
echo

# 5. .env 作成
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    echo "📝 .env を作成しました。API キーを入力してください:"
    echo "   - EODHD_API_KEY (必須)"
    echo "   - JQUANTS_REFRESH_TOKEN (必須)"
    echo "   - SEC_EDGAR_USER_AGENT (必須、メアド明記)"
    echo "   - FRED_API_KEY (必須)"
else
    echo "✅ .env は既に存在"
fi
echo

# 6. データディレクトリ作成
mkdir -p data/cache/{eodhd,jquants,sec_edgar,fred,polymarket}
mkdir -p data/{holdings/backups,decision-log,raw,exports}
mkdir -p reports
echo "✅ データディレクトリ準備完了"
echo

# 7. インストール確認
echo "🔍 主要パッケージのインポートテスト..."
uv run python -c "
import sys
packages = [
    'openbb', 'pandas', 'numpy', 'vectorbt', 'quantstats',
    'pandas_ta', 'streamlit', 'plotly', 'hmmlearn',
    'riskfolio', 'pypfopt', 'financedatabase', 'financetoolkit',
    'jquantsapi', 'httpx', 'pydantic_settings', 'loguru',
]
errors = []
for pkg in packages:
    try:
        __import__(pkg)
        print(f'  ✅ {pkg}')
    except ImportError as e:
        errors.append((pkg, str(e)))
        print(f'  ❌ {pkg}: {e}')
if errors:
    print(f'\\n⚠️  {len(errors)} 個のパッケージで import エラー')
    sys.exit(1)
print(f'\\n🎉 全 {len(packages)} パッケージ正常 import')
"
echo

# 8. 完了メッセージ
echo "═══════════════════════════════════════════════"
echo "🎉 kaori_kabu セットアップ完了！"
echo "═══════════════════════════════════════════════"
echo
echo "次のステップ:"
echo "  1. .env を編集して API キーを入力"
echo "     \$EDITOR .env"
echo
echo "  2. ダッシュボード起動"
echo "     uv run streamlit run src/dashboard/app.py"
echo
echo "  3. CLI で API 設定状況を確認"
echo "     uv run kabu status"
echo
