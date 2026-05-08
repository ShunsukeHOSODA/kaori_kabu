# kaori_kabu — かおりんの個人株運用ダッシュボード

> 世界トップ投資家の手法を AI で再現し、規律と統計で勝つ個人ローカルツール。

米国株 + 日本株を多角的視点（短期トレード / 長期投資 / 配当）で分析。Magic Formula / 13F Cloning / Monte Carlo / Half-Kelly / HMM レジーム検出 を組み合わせた MVP 7 機能を Streamlit ダッシュボードで提供する。

**完全に個人専用ローカル運用**（金商法対象外、投資助言サービスではない、すべて自己責任で売買判断）。

---

## 🎯 何ができるか（MVP 7 機能）

| # | 機能 | できること |
|---|---|---|
| 1 | Magic Formula スクリーナー | ROC + Earnings Yield で安く良い会社を抽出（Greenblatt） |
| 2 | 13F Cloning ダッシュボード | Berkshire / Pabrai / Burry / Ackman の最新ポジションを追従 |
| 3 | Monte Carlo 確率分布 | 1000 パスでポートフォリオ将来分布を fan chart 表示 |
| 4 | Half-Kelly ポジションサイザー | 数学的最適ポジション × 0.5 で破滅リスク抑制 |
| 5 | リスク指標 | Sharpe / Sortino / Calmar / Max DD / VaR / CVaR の一画面表示 |
| 6 | HMM レジーム検出 | Bull / Choppy / Crisis 自動判定（信号灯表示）|
| 7 | ATR トレーリングストップ | Loss Aversion バイアス対策の損切り強制リマインダー |

詳細: [`docs/product-requirements.md`](./docs/product-requirements.md)

---

## 🚀 最初の 10 分でやること

```bash
# 0. プロジェクトに移動
cd ~/Desktop/kaori_kabu

# 1. Python 環境作成（uv 推奨）
uv venv && source .venv/bin/activate
uv sync                                # pyproject.toml から依存をインストール
# uv 未インストール時: python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# 2. .env を作成して API キーを入力
cp .env.example .env
$EDITOR .env                          # EODHD_API_KEY と JQUANTS_REFRESH_TOKEN を入力

# 3. Streamlit ダッシュボード起動
streamlit run src/dashboard/app.py
# → http://localhost:8501 を自動で開く

# 4. （オプション）Claude Code で開発
claude
```

---

## 🔑 API キー取得手順

### EODHD（必須・米国 + 日本株）
1. https://eodhd.com/financial-apis/pricing
2. **EOD All World プラン $19.99/月** を選択
3. API トークンを `.env` の `EODHD_API_KEY` に設定

### J-Quants Light（必須・日本株の正本）
1. https://jpx-jquants.com で無料アカウント作成
2. **Light プラン 月 1,650 円** にアップグレード
3. リフレッシュトークンを `.env` の `JQUANTS_REFRESH_TOKEN` に設定

### SEC EDGAR（無料・米国 13F）
- API キー不要、**User-Agent ヘッダにメアド必須**
- `.env` の `SEC_EDGAR_USER_AGENT` に `Your Name your@email.com` を設定

### FRED（無料・米マクロ）
1. https://fred.stlouisfed.org/docs/api/api_key.html で無料発行
2. `.env` の `FRED_API_KEY` に設定

### Polymarket（無料・予測市場）
- `gamma-api.polymarket.com` は認証不要（60 req/min）

詳細: [`docs/onboarding.md`](./docs/onboarding.md)

---

## 📁 構造

```
kaori_kabu/
├── README.md / CLAUDE.md / AGENTS.md      ← Claude / 人間の context
├── pyproject.toml                          ← Python 依存定義
├── .env.example / .gitignore               ← 設定テンプレ
├── .claude/                                ← プロジェクト固有 Claude 設定
│   ├── settings.json                       ← hooks
│   ├── agents/kabu-analyst.md              ← データ + 分析統合エージェント
│   └── skills/                             ← 株運用特化 skill 群
│       ├── magic-formula-screener/
│       ├── monte-carlo-projection/
│       ├── 13f-cloning-tracker/
│       ├── kelly-position-sizer/
│       ├── regime-detection/
│       └── polymarket-macro-watcher/
├── docs/                                   ← 永続的ドキュメント
├── src/
│   ├── data/                               ← データ取得 (OpenBB / EODHD / J-Quants)
│   ├── analysis/                           ← 分析（Magic Formula, 13F, Risk）
│   ├── strategies/                         ← バックテスト戦略
│   ├── portfolio/                          ← ポートフォリオ管理・Kelly
│   ├── dashboard/                          ← Streamlit UI
│   │   └── app.py                          ← エントリーポイント
│   └── ui/                                 ← UI 共通コンポーネント
├── tests/                                  ← pytest（80%+ カバレッジ）
├── notebooks/                              ← Jupyter 探索用
├── data/
│   ├── cache/                              ← API キャッシュ（.gitignore）
│   ├── holdings/                           ← 保有銘柄 portfolio.csv（.gitignore）
│   └── decision-log/                       ← 売買判断ログ（.gitignore）
└── scripts/                                ← セットアップ・運用
```

詳細: [`docs/repository-structure.md`](./docs/repository-structure.md)

---

## 💰 月額コスト

| 項目 | 月額 | 必須度 |
|---|---|---|
| EODHD All World | $19.99 (≈3,000円) | ◎ |
| J-Quants Light | 1,650円 | ◎ |
| SEC EDGAR / FRED / Polymarket / OpenInsider | 0円 | ◎/◯ |
| **合計** | **約 4,500 円** | |

詳細: [`docs/cost-budget.md`](./docs/cost-budget.md)

---

## 🧠 設計思想

### 「素人 → 世界トップクラスに近づく」現実的な道筋

AI で **勝てない部分**：情報優位性 / 執行速度 / レバレッジ

個人が **勝てる土俵**：
- **規律** — Magic Formula を 5 年放置できる人は機関より少ない
- **長期視点** — 四半期決算プレッシャーがない
- **統計** — 13F + ファクターで「勝てるベットだけ」に絞る
- **小規模性** — 流動性の薄い小型バリューに参加できる

### 教育レイヤー（素人向け）

各シグナルに **3 段階表示**：
1. スコア（数値）
2. なぜそう判断するか（学術的バックボーン引用付き）
3. リスク警告 + 学習リソース

### 「予測」を確率分布で見せる

- 一本線の価格予測は禁止
- 必ず Monte Carlo 1000 パスの fan chart
- 5 / 50 / 95 パーセンタイル明示

---

## 📚 学習リソース

- Joel Greenblatt "The Little Book That Still Beats the Market"（Magic Formula）
- Mohnish Pabrai "The Dhandho Investor"（低リスク高不確実性）
- William Poundstone "Fortune's Formula"（Kelly Criterion）
- Aswath Damodaran "Investment Valuation"（DCF / 相対評価）
- Antti Ilmanen "Expected Returns"（ファクター投資）

---

## ⚠️ 免責事項

- 本ツールは個人専用の調査・分析支援であり、**投資助言ではない**
- 売買判断はすべてかおりん自身の責任で実施
- 表示される確率分布・シグナルは過去データに基づく統計的推定であり、将来を保証しない
- API データ提供元の遅延・誤り・規約変更により結果が変動する
- 損失について本ツールは一切の責任を負わない

---

## 🔗 関連リソース

- グローバル CLAUDE.md: `~/.claude/CLAUDE.md`
- グローバル AGENTS.md: `~/.claude/AGENTS.md`
- Obsidian vault: `~/Desktop/Obsidian/HOSODA_2nd_Brain`
- vault プロジェクトノート: `vault/notes/projects/kaori_kabu.md`
