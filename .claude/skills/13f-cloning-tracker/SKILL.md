---
name: 13f-cloning-tracker
description: SEC EDGAR から Berkshire Hathaway / Pabrai / Burry / Ackman 等のトップ投資家の 13F-HR を四半期取得し、保有銘柄の差分（新規買い / 増加 / 減少 / 売却）を分析する。Mohnish Pabrai の Dhandho 原則「Few Bets, Big Bets, Infrequent Bets」に基づき、5 銘柄以下のスーパー集中ファンドを優先表示。Use when ユーザーが「トップ投資家の保有銘柄」「Buffett の最新ポジション」「13F 追従」「クローン戦略」と発話したとき。
---

# 13F Cloning ダッシュボード

## 概要

機関投資家（運用資産 $100M 以上）は SEC に四半期で 13F-HR を提出する義務がある。45 日遅延だが、Buffett / Pabrai / Burry / Ackman のような著名投資家のポジションをほぼリアルタイムで追跡できる。

**学術的バックボーン**:
- Schroeder & Posch 2024: 3,643 ファンドのクローンが原ファンドにほぼ追従と実証
- Mohnish Pabrai "The Dhandho Investor": Dhandho 原則 = "heads I win, tails I don't lose much"

## 追跡対象ファンド（CIK）

| ファンド | 投資家 | CIK | 戦略 |
|---|---|---|---|
| Berkshire Hathaway | Warren Buffett | 0001067983 | Quality Value |
| Pabrai Investment Funds | Mohnish Pabrai | 0001173334 | 集中バリュー |
| Scion Asset Management | Michael Burry | 0001649339 | コントラリアン |
| Pershing Square | Bill Ackman | 0001336528 | アクティビスト |
| Greenlight Capital | David Einhorn | 0001079114 | ロング/ショート |

## 取得手順

### 1. SEC EDGAR API

```python
import httpx

headers = {"User-Agent": settings.SEC_EDGAR_USER_AGENT}
url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
response = httpx.get(url, headers=headers)
```

### 2. 13F-HR XML パース

infoTable 要素をパース。columns: nameOfIssuer, cusip, value (千ドル), sshPrnamt (株数), putCall。

### 3. 差分計算

`change_type`: NEW (新規買い) / INCREASE / DECREASE / EXIT (売却)

## 表示優先度

### 「スーパー集中ファンド」優先

Pabrai の Dhandho 原則で重視される 5 銘柄以下のスーパー集中ファンドを優先表示する。これらは「best ideas」を凝縮しており、個人投資家がコピーする価値が高い。

### 差分強調表示

```
🟢 NEW    Apple Inc.        $5.2B   +5.2B (新規買い)
🔵 INC    Coca-Cola         $3.8B   +0.5B (増加 +15%)
🟡 DEC    Wells Fargo       $2.1B   -0.3B (減少 -12%)
🔴 EXIT   IBM               $0      -1.5B (売却)
```

## 制約と注意

1. **45 日遅延**: 四半期末から 45 日後に提出義務、その時点では既に動いている
2. **ロングのみ**: ショートポジション・オプションは含まれない（Burry の Big Short も 13F では見えない）
3. **マネージャー判断**: ファンド内で誰がどの銘柄を担当しているかは不明
4. **キャッシュ**: 90 日キャッシュで API 負荷削減

## 完了時のチェックリスト

- [ ] User-Agent ヘッダ設定済み
- [ ] レート制限 10 req/秒 厳守
- [ ] 5 ファンド全て取得
- [ ] QoQ 差分計算
- [ ] スーパー集中ファンドを優先表示
- [ ] 13F の限界（遅延、ロングのみ）を併記
