# steering-example/ — 作業単位ドキュメントの雛形

新しい開発作業を始める時にこの 3 ファイルをコピーして使う。

## 使い方

```bash
# 新しい作業を始める時
mkdir -p .steering/$(date +%Y%m%d)-{タイトル}
cp steering-example/{requirements,design,tasklist}.md .steering/$(date +%Y%m%d)-{タイトル}/
```

## 命名

```
.steering/YYYYMMDD-kebab-case-title/
```

例:
- `.steering/20260507-add-tag-feature/`
- `.steering/20260601-fix-auth-bug/`
- `.steering/20260615-migrate-to-v2-api/`

## 流れ

1. **requirements.md** — 「今回は何を達成するか」
2. **design.md** — 「どう実装するか」（Plan Mode で生成 → 承認）
3. **tasklist.md** — 「具体的なタスク分解と進捗」

各ファイル**承認ゲート**を通す。LLM が一気にバッチ生成しないこと。

## 完了後

- 作業完了したら `.steering/.../` はそのまま履歴として残す
- 削除しない（後で「あの判断は何だったか」を振り返るため）
- 古いものが溜まったら `archive/` サブディレクトリに移動可
