# Runbook: ロールバック手順

## 判断基準

ロールバックする条件（OR）:

- 直近 30 分以内に deploy した
- 本番でエラー率 > 5%（直近 5 分）
- 主要機能が動かない（SEV-1 / SEV-2）
- セキュリティ問題が判明

ロールバックしない条件:
- すでに 24 時間以上経過した deploy（先送りリスクが上回る）
- マイグレーションで不可逆な変更を入れた（→ forward fix）

## Vercel のロールバック

### 方法 1: ダッシュボード

1. https://vercel.com/{org}/{project} → Deployments
2. 戻したい deployment の "..." → "Promote to Production"
3. ~30 秒で完了

### 方法 2: CLI

```bash
vercel rollback   # 直前へ
vercel rollback https://yourapp-xxxxxxxxx.vercel.app  # 特定 deploy
```

## Cloudflare Pages のロールバック

```bash
wrangler pages deployment list --project-name={プロジェクト}
wrangler pages deployment rollback <deployment-id>
```

## Git revert ベース（汎用）

```bash
# 最新 commit を revert
git revert HEAD --no-edit
git push origin main
# → CI 経由で revert された状態の deploy が走る
```

複数 commit 戻す:
```bash
git revert HEAD~3..HEAD --no-edit
git push origin main
```

## マイグレーションを含むロールバック

⚠️ **危険ゾーン**

DB スキーマ変更があった場合、コードを戻すだけでは不整合になる。

### 戦略

1. **backward-compatible マイグレーションを徹底**（基本方針）:
   - column 追加は OK（新コードのみ使う）
   - column 削除は **2 step**: コードから参照を消す → 後日 column 削除
   - データ型変更は新 column 追加 + dual write

2. **forward fix を選ぶケース**:
   - DB 変更が大きく rollback で破綻
   - hotfix で解決可能

3. **緊急 DB rollback（最終手段）**:
   - DBA に連絡
   - point-in-time recovery 検討

## 確認項目（rollback 後）

- [ ] `/health` が 200 OK
- [ ] エラー率が下降
- [ ] 主要機能の smoke test
- [ ] ユーザー影響の収束（status page 更新）

## 振り返り

ロールバックは「失敗」ではなく「正しい判断」。ただし：

- なぜ rollback が必要になったか（CI / レビューですり抜けた理由）
- 同じ問題を再発させない方法
- ポストモーテムに記録
