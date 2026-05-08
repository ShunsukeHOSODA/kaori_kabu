# 学習リソース — kaori_kabu

> 「他人の投資レシピをそのまま使うのが一番危険」— 学術的バックボーンを持って自分で判断する力をつけるためのリンク集。

---

## 📚 必読書（投資哲学・戦略）

| 書籍 | 著者 | 学べること |
|---|---|---|
| **The Little Book That Still Beats the Market** | Joel Greenblatt | Magic Formula 原典。ROC + Earnings Yield |
| **The Dhandho Investor** | Mohnish Pabrai | 集中バリュー投資、heads I win/tails I don't lose much |
| **Fortune's Formula** | William Poundstone | Kelly Criterion の歴史と実務 |
| **Investment Valuation** | Aswath Damodaran | DCF / 相対評価のバイブル |
| **Expected Returns** | Antti Ilmanen | ファクター投資の決定版 |
| **Margin of Safety** | Seth Klarman | 絶版だが PDF 流通、安全域思考 |
| **The Little Book of Behavioral Investing** | James Montier | 認知バイアス対策 |
| **A Man for All Markets** | Edward Thorp | Half-Kelly の実践、カジノ → ヘッジファンド |
| **Thinking, Fast and Slow** | Daniel Kahneman | 認知バイアスの古典 |

---

## 📄 必読論文

| タイトル | 著者・年 | テーマ |
|---|---|---|
| **The Cross-Section of Expected Stock Returns** | Fama & French 1992 | 3-factor モデル |
| **A Five-Factor Asset Pricing Model** | Fama & French 2015 | 5-factor 拡張（日本ではうまく機能しない） |
| **Outperforming the Market: 13F Cloning** | Schroeder & Posch 2024 | 3,643 ファンドの 13F クローン実証 |
| **Quality Minus Junk** | Asness et al. 2019 | Quality factor の定義 |
| **A Tutorial on Hidden Markov Models** | Rabiner 1989 | HMM の基礎、レジーム検出に必須 |
| **Information Aggregation in Prediction Markets** | Pennock 2004 | Polymarket の理論的バックボーン |
| **The Magic Formula in Japan** | Montier 2006 | 日本市場で +10.8% アウトパフォーム実証 |

---

## 🔧 採用した OSS（本リポジトリで利用）

| 名前 | スター | ライセンス | 役割 |
|---|---|---|---|
| [Streamlit](https://github.com/streamlit/streamlit) | ~35k | Apache-2.0 | UI フレームワーク |
| [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB) | ~33k | AGPL-3.0 | 100+ プロバイダ統合 |
| [Plotly Python](https://github.com/plotly/plotly.py) | ~17k | MIT | インタラクティブ可視化 |
| [vectorbt](https://github.com/polakowo/vectorbt) | ~7.3k | GPL-3.0 | Numba 高速バックテスト |
| [pandas-ta](https://github.com/twopirllc/pandas-ta) | ~5.5k | MIT | 150+ テクニカル指標 |
| [QuantStats](https://github.com/ranaroussi/quantstats) | ~5.4k | Apache-2.0 | リスク指標・tearsheet |
| [hmmlearn](https://github.com/hmmlearn/hmmlearn) | ~3.1k | BSD-3 | HMM レジーム検出 |
| [Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) | ~3.0k | BSD-3 | ポートフォリオ最適化 |
| [financedatabase](https://github.com/JerBouma/FinanceDatabase) | ~3.0k | MIT | 30 万銘柄マスタ |
| [FinanceToolkit](https://github.com/JerBouma/FinanceToolkit) | ~1.6k | MIT | 150+ 財務指標一括計算 ⭐ 新規追加 |
| [PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt) | ~4.5k | MIT | Mean-Variance / HRP |
| [arch](https://github.com/bashtage/arch) | ~1.3k | NCSA | GARCH ファミリー |
| [DuckDB](https://github.com/duckdb/duckdb) | ~24k | MIT | OLAP ローカル DB |
| [Polars](https://github.com/pola-rs/polars) | ~30k | MIT | 高速 DataFrame |

---

## 🎓 学習ロードマップ集（参照用、入れない）

### awesome-quant ⭐ ~19k（今回ブックマーク追加）

- **GitHub**: https://github.com/wilsonfreitas/awesome-quant
- **概要**: 量的金融 OSS の最大級リスト。Python / R / C++ / 各国データソース等を網羅
- **使い方**: 月 1 回チェックして「次に学ぶべき手法」を発見、kaori_kabu の Phase 2 / 3 機能候補を発掘

### awesome-systematic-trading

- **GitHub**: https://github.com/edarchimbaud/awesome-systematic-trading
- 戦略・データソース・論文の系統的リスト

### awesome-deep-trading

- **GitHub**: https://github.com/cbailes/awesome-deep-trading
- 機械学習・深層学習トレーディング論文集（Phase 3 以降の参考）

---

## 🧪 検討したが見送った OSS（理由付き）

| 名前 | スター | 見送り理由 |
|---|---|---|
| **FinGPT** | ~16k | 日本株対応薄い、Claude API 直接利用が筋良い |
| **FinRL**（強化学習） | ~10k | 研究用、個人本番には早すぎる |
| **QuantConnect Lean** | ~10k | C# ベース、Python 完結を崩す |
| **Hummingbot** | ~9k | 暗号資産用、対象外 |
| **Zipline** | ~18k | Quantopian 倒産で開発停滞 |
| **TA-Lib** (C 版) | ~9.5k | pandas-ta で代替、ビルド面倒 |
| **backtesting.py** | ~5.5k | vectorbt と機能重複、開発鈍化 |
| **TradingView Lightweight Charts** | ~10k | Plotly で代替可 |
| **Pyfolio (original)** | ~5.5k | メンテ停止、QuantStats が後継 |

---

## 🎯 投資家別の追跡ファンド（13F Cloning）

| 投資家 | ファンド | CIK | 戦略 |
|---|---|---|---|
| Warren Buffett | Berkshire Hathaway | 0001067983 | Quality Value |
| Charlie Munger | Daily Journal | 0000783412 | 集中バリュー（小規模） |
| Mohnish Pabrai | Pabrai Investment Funds | 0001173334 | Dhandho 集中 |
| Michael Burry | Scion Asset Management | 0001649339 | コントラリアン |
| Bill Ackman | Pershing Square | 0001336528 | アクティビスト |
| David Einhorn | Greenlight Capital | 0001079114 | ロング/ショート |
| Seth Klarman | Baupost Group | 0001061768 | 安全域 |
| Howard Marks | Oaktree Capital | 0000949509 | デットバリュー |
| Joel Greenblatt | Gotham Asset Management | 0001423053 | Magic Formula 創始者 |

---

## 📊 主要データソース公式ドキュメント

| ソース | URL | 月額 |
|---|---|---|
| **EODHD** | https://eodhd.com/financial-apis/api-documentation | $19.99 |
| **J-Quants** | https://jpx.gitbook.io/j-quants-ja | 1,650 円 |
| **SEC EDGAR** | https://www.sec.gov/edgar/sec-api-documentation | 無料 |
| **FRED** | https://fred.stlouisfed.org/docs/api/fred/ | 無料 |
| **Polymarket Gamma** | https://docs.polymarket.com/ | 無料 |
| **EDINET** | https://disclosure2.edinet-fsa.go.jp/WEEK0010.aspx | 無料 |
| **e-Stat** | https://www.e-stat.go.jp/api/ | 無料 |

---

## 🧠 認知バイアス対策（必読）

- **Loss Aversion**（損失回避）→ ATR トレーリングストップで強制
- **Confirmation Bias**（確証バイアス）→ 反対意見を必ず読む
- **Recency Bias**（直近バイアス）→ 5 年以上のヒストリカル必須
- **Overconfidence**（自信過剰）→ Half-Kelly でレバレッジ抑制
- **Anchoring**（アンカリング）→ 取得価格を見ずに判断
- **Disposition Effect**（保有株を売れない）→ Decision Log で振り返り

参考: Daniel Kahneman "Thinking, Fast and Slow"

---

## 🔄 更新タイミング

このファイルは月 1 回（毎月初）見直し。新しく学んだリソースを追加し、使わなくなったものは削除する。
