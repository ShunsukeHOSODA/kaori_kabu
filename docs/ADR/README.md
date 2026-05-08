# Architecture Decision Records (ADR)

技術選定や設計判断の根拠を記録する。**変更されない歴史的事実**として保管。

## なぜ ADR か

- なぜ X を選んだか / なぜ Y を選ばなかったかが将来分からなくなる
- 同じ議論を何度もやり直すのを防ぐ
- 新メンバー / Claude が「なぜこうなってるか」を理解できる

## 命名

```
NNNN-short-title.md
```

例:
- `0001-initial-stack.md`
- `0002-monorepo-vs-polyrepo.md`
- `0003-orm-drizzle-over-prisma.md`

連番は重複しないこと。

## 書き方

[`template.md`](./template.md) を雛形に：

1. 番号取得（既存の最大 + 1）
2. ファイル作成
3. PR で議論
4. 承認後 merge（ステータス: accepted）

## ステータス

- **proposed**: 提案中（議論中）
- **accepted**: 採用済み（実装中・実装済み）
- **superseded**: より新しい ADR で置き換えられた（番号と link を記載）
- **deprecated**: 使われなくなった（理由を追記）

## 例

サンプル: [`0001-initial-stack.md.example`](./0001-initial-stack.md.example)
