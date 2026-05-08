# セキュリティ

> **前提**: 一般的セキュリティは `~/.claude/rules/common/security.md` + `security-review` スキルに委譲。このファイルは脅威モデルとプロジェクト固有の対策。

## 脅威モデル（STRIDE）

| カテゴリ | 例 | 対策 |
|---|---|---|
| **S**poofing（なりすまし） | 認証バイパス、セッション乗っ取り | OAuth2/OIDC、HttpOnly Cookie、CSRF token |
| **T**ampering（改ざん） | リクエスト書き換え、SQL injection | パラメータ化クエリ、HMAC、TLS |
| **R**epudiation（否認） | 操作履歴改ざん | 監査ログ（append-only） |
| **I**nformation Disclosure | PII 漏洩、ログ漏洩 | 暗号化、最小権限、PII マスキング |
| **D**enial of Service | 過負荷、リソース枯渇 | rate limit、CDN、circuit breaker |
| **E**levation of Privilege | 権限昇格 | RBAC、deny-by-default、審査必要操作 |

## 認証 / 認可

### 認証

- **OAuth2 / OIDC のみ**（自前パスワード認証は禁止 — `Better Auth` 等使用）
- セッション: HttpOnly + SameSite=Lax/Strict + Secure Cookie
- MFA は管理者必須、一般ユーザーは optional

### 認可（RBAC）

```typescript
// 例
const ROLES = {
  user: ['task.read', 'task.create:own', 'task.update:own'],
  admin: ['task.*', 'user.*'],
} as const;

function authorize(user: User, action: string, resource: Resource): boolean {
  // ...
}
```

- **deny-by-default**: 明示的に許可されていない操作はすべて拒否
- リソース所有チェック（`:own` suffix）

## 入力検証

**全入力をスキーマで検証**（zod / pydantic / etc.）：

```typescript
// 例
const CreateTaskSchema = z.object({
  title: z.string().min(1).max(200),
  due_date: z.string().datetime().optional(),
  tags: z.array(z.string()).max(10),
});

const input = CreateTaskSchema.parse(req.body);  // throws on invalid
```

- バリデーションは **エンドポイント直後**で実施
- DB 層でも制約（NOT NULL, CHECK constraint）

## OWASP Top 10 対応

| カテゴリ | 対策 |
|---|---|
| A01 Broken Access Control | RBAC + リソース所有チェック |
| A02 Cryptographic Failures | TLS 1.2+、bcrypt/argon2、KMS |
| A03 Injection | パラメータ化クエリ、入力検証 |
| A04 Insecure Design | このファイルの脅威モデル化 |
| A05 Security Misconfiguration | CSP、HSTS、X-Frame-Options |
| A06 Vulnerable Components | `npm audit`、Dependabot |
| A07 Auth Failures | OAuth/OIDC、セッション管理 |
| A08 Data Integrity | サブリソース完全性（SRI）、署名検証 |
| A09 Logging Failures | 構造化ログ、改ざん防止 |
| A10 SSRF | URL allowlist、内部 IP block |

## CSP（Content Security Policy）

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-{RANDOM}' https://trusted-cdn.com;
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  connect-src 'self' https://api.example.com;
  frame-src 'none';
  object-src 'none';
  base-uri 'self';
```

詳細: `~/.claude/rules/web/security.md`

## HTTPS / セキュリティヘッダー

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

## PII（個人情報）の取り扱い

- 保存時暗号化（pgcrypto / KMS / AWS RDS encrypted）
- ログに出さない（マスキング）
- 開発・テスト DB に本番データを使わない（合成データ生成）
- 法務要件: GDPR / APPI 対応（地域による）

## Secret 管理

- **NEVER** ソースコード commit
- 開発: `.env`（gitignore 済み）
- 本番: Vercel/Cloudflare 等の secret manager
- ローテーション: 90 日（推奨）、漏洩時は即時

## 依存関係セキュリティ

- `npm audit` を CI で必須（HIGH/CRITICAL 0 維持）
- Dependabot / Renovate で自動 PR
- ライブラリ追加時のセキュリティレビュー

## ペネトレーションテスト

- リリース前 1 回（本番前）
- 主要機能変更時
- ツール: Burp Suite / OWASP ZAP

## インシデント対応

詳細: [`runbooks/incident-response.md`](./runbooks/incident-response.md)

漏洩疑い時：

1. 即時遮断（影響アカウントロック、関連 API キー無効化）
2. 影響範囲調査（誰の / 何の / どれだけ）
3. ログ保全（改ざん防止）
4. 関係者通知（法的要件、72 時間以内が多い）
5. 事後分析（ADR で記録）

## このプロジェクトの追加要件

- {例: 会員の決済情報は PCI DSS 準拠サードパーティに委譲、自社で保存しない}
- {例: 管理画面は IP 制限 + 2 要素認証必須}
