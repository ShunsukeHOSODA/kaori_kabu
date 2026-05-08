# オンボーディング — 新規参画者向け

> **対象**: 新メンバー（人間）+ 新セッションの Claude Code

## 1. 環境セットアップ（人間）

### 必須ツール

```bash
# macOS の例（Homebrew 必須）
brew install node@20 pnpm git gh jq

# Claude Code
# https://docs.claude.com/claude-code

# 認証
gh auth login
claude  # アカウントログイン
```

### リポジトリ取得

```bash
gh repo clone {org}/{プロジェクト名}
cd {プロジェクト名}
cp .env.example .env
$EDITOR .env  # 必要なキーを記入
pnpm install
pnpm dev
```

## 2. 必読ドキュメント（30 分）

順番に読む：

1. [`README.md`](../README.md) — このリポジトリ全体の navigation
2. [`CLAUDE.md`](../CLAUDE.md) — Claude / 人間共通の context
3. [`docs/product-requirements.md`](./product-requirements.md) — 何を作っているか
4. [`docs/functional-design.md`](./functional-design.md) — どう作っているか
5. [`docs/architecture.md`](./architecture.md) — 技術選定
6. [`docs/development-guidelines.md`](./development-guidelines.md) — プロジェクト固有ルール
7. [`docs/glossary.md`](./glossary.md) — 用語

## 3. Claude Code セッション開始（30 分）

### 初回起動

```bash
cd {プロジェクト名}
claude
```

Claude が自動で：
- `CLAUDE.md` をロード
- `docs/` の存在確認
- `.steering/` の進行中タスク確認
- vault（Obsidian）から関連プロジェクト履歴を引く

### 自分の慣らし運転

最初の 1-2 セッションは小さなタスクで試す：

- ドキュメント typo 修正
- README の補足追記
- 既存テストにケース追加
- 既存コンポーネントの a11y 改善

## 4. ワークフロー（人間）

```
新機能 / バグ修正
   ↓
.steering/[YYYYMMDD]-[title]/ 作成
   ↓
requirements.md → design.md → tasklist.md（1 ファイル毎承認）
   ↓
Plan Mode（Shift+Tab × 2）で確認
   ↓
TDD で実装（superpowers:test-driven-development）
   ↓
code-reviewer + 言語別 reviewer
   ↓
PR 作成（@claude タグで自動レビュー）
   ↓
CI pass → squash merge
```

## 5. ヘルプ

| 困りごと | 行き先 |
|---|---|
| プロジェクト固有のルール | `CLAUDE.md` + `docs/development-guidelines.md` |
| ドメイン用語 | `docs/glossary.md` |
| エージェント呼び方 | `AGENTS.md` |
| Obsidian vault | `~/Desktop/Obsidian/HOSODA_2nd_Brain` |
| 過去の議論・決定 | `docs/ADR/` |
| 障害時の動き方 | `docs/runbooks/incident-response.md` |
| 質問できる相手 | {Slack チャンネル / 担当者} |

## 6. 最初の PR

最初の PR は小さく：

- 影響範囲が小さい
- テスト追加できる
- レビュー時に基本ワークフローを学ぶ

example:

- 既存ドキュメントの軽微な修正
- 自分の名前を CODEOWNERS に追加
- README に「困った時の連絡先」を追記

## 7. Claude Code を使い始める Tips

- **Plan Mode 必須**: `Shift+Tab` × 2 で Read-only モードに入る、変更前に必ず使う
- **Subagent 活用**: 探索は `Explore` agent に任せる
- **並列実行**: 独立タスクは 1 メッセージに複数 Agent
- **詰まったら**: `/superpowers:brainstorming` で要件を表面化
- **コンテキスト管理**: 50% 超えたら `/clear`、トピック変える時は新セッション

## 8. 参考リソース

- グローバル設定: `~/.claude/CLAUDE.md`
- Karpathy 流: `andrej-karpathy-skills`
- 規律的ワークフロー: `superpowers/`
- 最新の Claude Code 機能: https://docs.claude.com/claude-code
