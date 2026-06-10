# セキュリティポリシー / Security Policy

[日本語](#日本語) | [English](#english)

---

## 日本語

### 脆弱性の報告

fuseji の脆弱性を発見された場合は、**公開 Issue では報告せず**、以下のいずれかの非公開チャネルでご連絡ください。

- **GitHub Security Advisory**: [https://github.com/sserada/fuseji/security/advisories/new](https://github.com/sserada/fuseji/security/advisories/new)
- メール: serada.dev@gmail.com

### 対応 SLA（目安）

- **初動応答**: 5 営業日以内
- **深刻度の評価とパッチ計画**: 14 営業日以内
- **重大な脆弱性の修正リリース**: 評価後 30 日以内

### サポート対象バージョン

| バージョン | サポート |
| --- | --- |
| `0.1.x` | ✓（最新マイナー） |
| `< 0.1` | ✗（pre-release） |

---

### 設計上の安全保証

fuseji は **検出・破棄するが保持しない（detect, never retain）** ことを設計原則としています。

#### 1. PII の永続化なし

- 検出値はメモリ上の `Entity` オブジェクトとしてのみ保持され、ディスク・データベース・ログには書き出しません
- ライブラリ自体はネットワーク I/O を行いません

#### 2. Vault は session-scoped

- `InMemoryVault` はプロセスメモリ内のみで対応表を保持
- 永続化（DB/Redis 連携等）はユーザー責任。fuseji は永続化機構を提供しません

#### 3. マイナンバー（My Number）の特別扱い

**`MY_NUMBER` は `InMemoryVault` のデフォルト除外集合に含まれており、復元できません。**

```python
from fuseji import InMemoryVault
InMemoryVault.DEFAULT_EXCLUDED_TYPES
# frozenset({'MY_NUMBER'})
```

`vault.assign("MY_NUMBER", ...)` は `None` を返し、対応表に残しません。Masker が `vault=...` を受け取った場合、`MY_NUMBER` は番号なしの固定 placeholder `<MY_NUMBER>` でマスクされ、`vault.restore()` でも復元されません。

これは **マイナンバー法（行政手続における特定の個人を識別するための番号の利用等に関する法律）** 上、fuseji が「個人番号を取り扱う」とみなされないよう、検出と同時に破棄する設計判断です。

ユーザーが意図的に復元を必要とする場合は、明示的に `InMemoryVault(excluded_types=[])` を指定する必要があります（番号法上のリスクは利用者側に帰属します）。

#### 4. Langfuse アダプタの fail-closed

`make_mask_fn()` は内部例外を捕捉して固定 placeholder `"[fuseji: masking failed]"` を返します。原データは絶対に返却しません。

```python
from fuseji.integrations.langfuse import make_mask_fn

mask_fn = make_mask_fn()
mask_fn("...")  # 例外時は "[fuseji: masking failed]"
```

例外内容は WARNING ログに記録されます（ログ集約側で原データが PII を含まないよう注意してください）。

#### 5. 認識器の境界

正規表現認識器は ReDoS（catastrophic backtracking）フリーになるよう設計されています。
すべてのパターンに固定上限（`{12}`, `{12,18}`, `{8,10}` 等）を設けており、入力長 n に対し O(n) で完結します。

#### 6. 検出の確実性

`MY_NUMBER` 認識器は **recall 優先** で、チェックディジット不一致でも `score=0.5` で検出します。デフォルト `threshold=0.4` のため、これらもマスク対象となります。これは番号法上「漏らさない」ことを最優先する設計です。

### 利用者側の責任範囲

fuseji は **in-flight masking** のみを提供します。以下は利用者側の責任です:

- **保持と廃棄**: `Entity.text` を含む `MaskResult.entities` をログ出力・永続化しないこと
- **Vault 永続化**: `InMemoryVault` を DB/Redis 等に展開する場合の暗号化・アクセス制御
- **マッピングテーブルの保護**: `MaskResult.mapping` も placeholder ↔ 原データ対応表として PII 同等の取り扱い
- **入力テキストの取り扱い**: マスク前の原テキストの保存・転送
- **fuseji 例外時のフォールバック**: アプリケーション側で `try/except` を併用するか、Langfuse アダプタ等の fail-closed 経路を使用すること

### 既知の脅威モデル

| 脅威 | 対応状況 |
| --- | --- |
| fuseji 内部での PII 永続化 | 設計上ゼロ |
| マイナンバーの復元 | デフォルト除外で不可（明示的に上書き可） |
| Vault のメモリ上対応表流出 | 利用者責任（プロセスメモリ管理） |
| 認識漏れ（false negative） | recall 優先設計で抑制、ベンチマークで継続改善 |
| 誤検出（false positive） | 過剰マスクは許容（PII 漏洩より低リスク） |
| ReDoS | 認識器設計でフリー |
| サーバーモードの DoS | リクエストサイズ・タイムアウト制限は Issue #29 で対応中 |

---

## English

### Reporting a vulnerability

If you discover a security vulnerability in fuseji, please **do not open a public issue**. Report it through one of these private channels:

- **GitHub Security Advisory**: [https://github.com/sserada/fuseji/security/advisories/new](https://github.com/sserada/fuseji/security/advisories/new)
- Email: serada.dev@gmail.com

### Response SLA (target)

- **Initial response**: within 5 business days
- **Severity assessment and patch plan**: within 14 business days
- **Critical vulnerability fix release**: within 30 days after assessment

### Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` | ✓ (latest minor) |
| `< 0.1` | ✗ (pre-release) |

### Design-time safety guarantees

fuseji follows **detect, never retain**:

1. **No PII persistence**: detected values live only in `Entity` objects in memory; never written to disk/db/logs. The library performs no network I/O.
2. **Session-scoped vault**: `InMemoryVault` keeps mappings only in process memory. Persistence (DB/Redis) is the caller's responsibility.
3. **My Number is excluded by default**: `MY_NUMBER` is in `InMemoryVault.DEFAULT_EXCLUDED_TYPES`. `vault.assign("MY_NUMBER", ...)` returns `None` and is never stored. This is intentional for Japanese Number Act (番号法) compliance — fuseji must not "handle" the number in legal terms.
4. **Fail-closed Langfuse adapter**: `make_mask_fn()` catches all exceptions and returns the fixed placeholder `"[fuseji: masking failed]"`. Original data is never returned.
5. **ReDoS-free**: all regex patterns have bounded quantifiers; runtime is O(n) in input length.
6. **Recall-biased detection**: `MY_NUMBER` recognizer emits matches even when the checksum fails (score 0.5), to minimize leakage risk.

### Caller responsibilities

fuseji provides **in-flight masking only**. The caller is responsible for:

- Not logging/persisting `Entity.text` from `MaskResult.entities`
- Encrypting and access-controlling any persistence of `InMemoryVault` state
- Treating `MaskResult.mapping` as PII-equivalent (it links placeholders to originals)
- Securing the original text before masking
- Using `try/except` or the Langfuse adapter's fail-closed path
