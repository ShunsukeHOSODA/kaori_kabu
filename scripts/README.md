# scripts/

プロジェクト固有のセットアップ・テスト・運用スクリプト。

| ファイル | 用途 |
|---|---|
| `setup.sh` | 開発環境の初回セットアップ |
| `test-all.sh` | 全テスト実行（unit + integration + e2e + lint + typecheck） |
| `pre-deploy-check.sh` | デプロイ前の最終チェック |

## 使い方

```bash
chmod +x scripts/*.sh
bash scripts/setup.sh
```

## 規約

- **POSIX shell or bash** で書く（zsh-only 機能を使わない）
- `set -euo pipefail` を冒頭に
- エラー時は人間が読めるメッセージを出す
- 進捗を echo で出す（`✓ done` / `✗ failed`）
- 90 行以内（複雑なら別ファイルに分ける）

## サンプルファイルの使い方

`.example` 拡張子付きはサンプル。実際に使うときは：

```bash
cp scripts/setup.sh.example scripts/setup.sh
chmod +x scripts/setup.sh
```
