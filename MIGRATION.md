# 移行ガイド / Migration Guide

[日本語](#日本語) | [English](#english)

---

## 日本語

### 対象: v0.2.x → v0.3 アップグレード

v0.3 は **5 件の breaking change** を含みます。基本 API (`Masker`, `Masker.mask`, `Masker.mask_json`) は不変ですが、戻り値や repr の振る舞いが変わるため、テスト・ログ・API クライアントに影響しうる経路があります。

#### Quick checklist

以下に 1 つでも当てはまれば、該当セクションの手順を確認してください:

- ☐ `repr(Entity)` / `repr(MaskResult)` の文字列に依存するテスト・ログを書いている → **#1**
- ☐ FastAPI サーバーの `POST /detect` レスポンスで `entities[].text` を使っている → **#2**
- ☐ `FakerStrategy` をマルチプロセスで使い、同じ surface に同じ fake を返すことを期待 → **#3**
- ☐ `FakerStrategy.mask()` の戻り値 `mapping` から元 PII を取り出している → **#4**
- ☐ `InMemoryVault` の placeholder 長 (8 文字 nonce 部分) に依存するテキスト処理 → **#5**

全部 ☐ のままなら、移行作業は不要です。

---

#### 1. `Entity` / `MaskResult` の `__repr__` が PII safe に (#144)

**症状**: `repr(entity)` が `Entity(type='EMAIL', text='taro@example.com', ...)` ではなく `Entity(type='EMAIL', text=<len=16 hash=fb98d44a>, ...)` を返すようになります。

**検知方法**: テストで `assert "taro@example.com" in repr(entity)` のような assertion がある場合、v0.3 で fail します。

**修正手順**:
- デバッグ目的で原 surface が必要なら → `entity.unsafe_repr()` を opt-in で呼ぶ
- 値そのものを取り出したいだけなら → `entity.text` を直接参照

```python
# Before (v0.2):
print(repr(entity))
# Entity(type='EMAIL', text='taro@example.com', ...)

# After (v0.3) — safe デフォルト:
print(repr(entity))
# Entity(type='EMAIL', text=<len=16 hash=fb98d44a>, ...)

# デバッグ用 opt-in:
print(entity.unsafe_repr())  # 原 PII を含む

# 値だけ取りたいなら直接参照:
print(entity.text)
```

---

#### 2. `POST /detect` レスポンスから原 PII surface をデフォルト除去 (#143)

**症状**: `DetectResponse.entities[].text` がデフォルトで `null` を返すようになります (旧: 原 surface)。

**検知方法**: クライアントが `response.entities[i].text` を読んでマスク済みテキストを再構築している場合、`null` を受け取って壊れます。

**修正手順** (どちらか):

A. **クライアントを直す** (推奨): `start` / `end` でクライアント側の原テキストから抜き出す

```python
# Before (v0.2): サーバーから原 surface を受信
masked_text = client_text.replace(entities[i].text, "<MASK>")

# After (v0.3): start/end から原テキストを抜く
for e in response.entities:
    masked_text = masked_text[:e.start] + "<MASK>" + masked_text[e.end:]
```

B. **サーバーで opt-in 有効化**: `create_app(detect_include_surface=True)` または環境変数 `FUSEJI_DETECT_INCLUDE_SURFACE=1`。ただし `MY_NUMBER` / `CREDIT_CARD` / `CORPORATE_NUMBER` は opt-in 時も `<redacted>` 固定。

---

#### 3. `FakerStrategy` のデフォルト salt がインスタンス毎ランダム (#145)

**症状**: `FakerStrategy()` (salt 未指定) が毎回別の salt を生成するため、**プロセスを跨ぐと同じ surface から異なる fake が返ります**。

**検知方法**: マルチプロセス / 分散実行 / 永続化 された fake → 原 PII の対応に依存していた場合、再起動後に対応が壊れます。

**修正手順**: 永続化が必要なら **salt を明示的に渡す** (秘密として保護):

```python
import os
strategy = FakerStrategy(salt=os.environ["FUSEJI_FAKER_SALT"])  # シークレットマネージャから取得
```

salt は `repr(strategy)` で `<redacted>` 表示されます (ログ漏洩から保護)。詳細は [`docs/integrations/faker.md`](docs/integrations/faker.md)。

---

#### 4. `FakerStrategy.keep_mapping` を opt-in 化 (#139)

**症状**: `FakerStrategy().mask(text, entities)` が返す `mapping` がデフォルトで空 dict になります (旧: `{fake: 元 surface}`)。

**検知方法**: `mapping[fake_value]` で元 PII を取得していた場合、`KeyError` になります。

**修正手順**: 旧挙動が必要なら明示的に opt-in:

```python
strategy = FakerStrategy(keep_mapping=True)
result = masker.mask(text)
result.mapping  # 従来通り {fake: 元 surface}
```

ただし `mapping` は **PII 同等のセンシティブ情報** として扱ってください (ログ出力 / 永続化に注意)。Hash 戦略の `keep_mapping=False` デフォルトと整合する設計。

---

#### 5. `InMemoryVault` の nonce が 32-bit → 128-bit に (#185)

**症状**: `vault.assign()` が返す placeholder が `<PERSON_1_a1b2c3d4>` (16 + 8 文字) から `<PERSON_1_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6>` (16 + 32 文字) になります。

**検知方法**: placeholder 長を assert しているテスト、または **payload size 制限ギリギリ** で運用していた経路で影響。

**修正手順**:
- テストで長さ assert している場合は新しい長さに合わせる、もしくは正規表現で構造マッチに変更
- payload size が圧迫される場合は対象 PII 数を見直す (1 placeholder あたり 24 文字増)
- 明示指定 `InMemoryVault(nonce="test")` は影響なし

---

### Roll-back / 部分有効化

各 breaking change は独立 opt-in / opt-out で操作可能:

| 変更 | 旧挙動に戻す方法 |
| --- | --- |
| #144 repr safe | `entity.unsafe_repr()` を呼ぶ |
| #143 detect redact | `create_app(detect_include_surface=True)` |
| #145 salt random | `FakerStrategy(salt="...")` を明示 |
| #139 mapping opt-in | `FakerStrategy(keep_mapping=True)` |
| #185 Vault nonce | `InMemoryVault(nonce="...")` で 8 文字も指定可 |

---

### 参考

- 全ての変更の詳細: [CHANGELOG.md](CHANGELOG.md)
- 設計の意図: [SECURITY.md](SECURITY.md) §7-§9
- 各統合の運用ガイド: [docs/integrations/](docs/integrations/)
- ロードマップ: [ROADMAP.md](ROADMAP.md)

---

## English

### Target: v0.2.x → v0.3 upgrade

v0.3 ships **5 breaking changes**. Core API (`Masker`, `mask`, `mask_json`) is unchanged, but behaviors around repr, response payloads, and Faker determinism may affect tests, logs, and API clients.

#### Quick checklist

If any of the following applies, follow the relevant section below:

- ☐ Your tests / logs depend on the string form of `repr(Entity)` / `repr(MaskResult)` → **#1**
- ☐ Your FastAPI client reads `entities[].text` from `POST /detect` → **#2**
- ☐ You use `FakerStrategy` across processes and expect identical fakes for identical surfaces → **#3**
- ☐ You extract original PII from `FakerStrategy.mask()` `mapping` return value → **#4**
- ☐ Your code depends on `InMemoryVault` placeholder length (8-char nonce part) → **#5**

If all boxes are unchecked, no migration work is required.

#### 1. `Entity` / `MaskResult` `__repr__` is now PII-safe (#144)

`repr(entity)` no longer contains the raw surface. Use `entity.unsafe_repr()` for debugging or `entity.text` for the raw value.

#### 2. `POST /detect` strips raw PII surface by default (#143)

`entities[].text` returns `null` by default. Either reconstruct via `start` / `end` on the client, or opt in with `create_app(detect_include_surface=True)` / `FUSEJI_DETECT_INCLUDE_SURFACE=1`.

#### 3. `FakerStrategy` default salt is randomized per instance (#145)

For cross-process determinism, pass an explicit salt (treat as secret):

```python
strategy = FakerStrategy(salt=os.environ["FUSEJI_FAKER_SALT"])
```

#### 4. `FakerStrategy.keep_mapping` is now opt-in (#139)

`mask()` returns an empty `mapping` by default. Pass `keep_mapping=True` for the old behavior; treat the mapping as PII-equivalent.

#### 5. `InMemoryVault` nonce widened from 32-bit to 128-bit (#185)

Placeholders are 24 chars longer. Update length-based assertions or watch payload size budgets.

### References

- Full change log: [CHANGELOG.md](CHANGELOG.md)
- Design rationale: [SECURITY.md](SECURITY.md) §7-§9
- Per-integration operations: [docs/integrations/](docs/integrations/)
- Roadmap: [ROADMAP.md](ROADMAP.md)
