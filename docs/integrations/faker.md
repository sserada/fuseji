# FakerStrategy 運用ガイド

[Faker](https://github.com/joke2k/faker) (ja_JP) で PII を **架空値** に置換する戦略 (#128)。LLM オブザーバビリティで「実テキストっぽい形を保ったまま PII を伏せたい」用途に向く。本ページは production 運用で押さえるべきポイントをまとめる。詳細な API は [`docs/api.md`](../api.md#fakerstrategyfaker-extra-必須128)。

## インストール

```bash
pip install 'fuseji[faker]'
```

`[faker]` extra は `Faker>=24.0` を引きます。

## 典型的な利用パターン

```python
from fuseji import Masker
from fuseji.faker_strategy import FakerStrategy

masker = Masker(strategy=FakerStrategy())
result = masker.mask("田中さん 連絡先 taro@example.com まで")
print(result.text)
# 例: '佐藤花子さん 連絡先 user@example.org まで'
```

`PERSON` → ja_JP の人名、`EMAIL` → RFC 6761 reserved domain (`example.com/.org/.net`)、`JP_PHONE_NUMBER` → 安全な fictitious format (`070-0000-XXXX` 等)、`JP_POSTAL_CODE` → `999-XXXX` 局番に置換されます。

## salt の運用 (#145)

`FakerStrategy.salt` は決定的モード (`deterministic=True`、デフォルト) で `surface → fake` 写像を決めるソルト。**デフォルトはインスタンス毎の `secrets.token_hex(32)` (128-bit) でランダム生成**されます。これによりソース固定の salt による fake → surface 辞書攻撃を構造的に塞ぐ設計。

### マルチプロセス決定性が必要な場合のみ明示

異なるプロセス / 異なるインスタンスで **同じ surface に同じ fake** を返したい用途 (永続化 / 分散実行 / 監査ログの整合性) では、salt を明示的に渡します。

```python
import os
strategy = FakerStrategy(salt=os.environ["FUSEJI_FAKER_SALT"])  # 秘密として保護
```

- 環境変数 / シークレットマネージャから取得し、ソースコードや log には書き出さない
- 同一プロセス内の決定性は salt 自動生成でも保証 (内部キャッシュ経由)
- `repr(strategy)` は salt を `<redacted>` で隠蔽

### 逆引き耐性の限界

FakerStrategy は LLM オブザーバビリティの **可読性向上** が主目的で、暗号学的な逆引き保護は提供しません。攻撃者が salt と fake を両方知っている場合、候補 surface 集合の辞書攻撃で逆引きが可能です。

**暗号学的保護が必要な場合は [`Hash`](../api.md#hash) 戦略を使い、salt を秘密として扱ってください。**

## mapping の取扱い (#139)

`MaskResult.mapping` (= `{fake: 元 surface}`) は **デフォルトで空 dict** を返します (`keep_mapping=False`)。これは Hash 戦略と整合させた「detect, never retain」原則: LLM trace / Langfuse / OTel の attribute に MaskResult.mapping を書き出すパスで原 PII が漏出する経路を遮断するためです。

復元が必要な用途では明示的に opt-in します:

```python
strategy = FakerStrategy(keep_mapping=True)
result = masker.mask("田中さん")
print(result.mapping)
# {'佐藤花子': '田中さん'} など
```

`keep_mapping=True` を使うときは、mapping を **PII 同等のセンシティブ情報として** 扱ってください (ログ出力 / 永続化に注意)。

## 再検出問題と固定マスク

Faker 生成値は fuseji 認識器が再度 PII として検出する形式になりうるため、以下の type は **固定マスク `<MASKED>` で置換** されます:

- `MY_NUMBER` (番号法対応)
- `CREDIT_CARD` (Luhn 通過の架空 CC を出さない、PCI DSS 3.4 対応)
- `CORPORATE_NUMBER` (国税庁公開仕様 checksum を通る架空番号を避ける)

電話番号 / 郵便番号は再検出されても問題ない形式 (`070-0000-XXXX` / `999-XXXX`) で生成しています。

## キャッシュ運用 (#142 / #177)

決定的モードでは `(entity_type, surface) → fake` を内部キャッシュに保持し、同一 surface の繰り返し検出で `Faker` インスタンス再構築コスト (数 ms〜十数 ms) を回避します。

| 設定 | デフォルト | 説明 |
| --- | --- | --- |
| `max_cache_size` | `8192` | LRU 上限。超過時に最古アクセスを破棄 |
| `0` を指定 | 無制限 | 旧挙動 (長時間稼働でメモリ単調増加に注意) |

長時間稼働するサーバーで高カードナリティ surface (例: ランダム email) が継続流入する場合、デフォルト 8192 でメモリは bounded のまま保たれます。

## Hash 戦略との使い分け

| 用途 | 推奨 |
| --- | --- |
| LLM 提示時の **可読性** を保ちたい | `FakerStrategy` |
| **逆引き耐性** が必要 (salt を秘密として運用) | `Hash` |
| 復元が必要な永続化用途 (Vault と組み合わせ) | `VaultStrategy` |
| 完全に伏せたい (固定文字列) | `Redact` |

## 参考

- 関連 PR: #128 (導入), #139 (mapping opt-in), #142 (faker holder), #145 (salt random), #177 (cache bound)
- 設計討議: [`docs/api.md`](../api.md#fakerstrategyfaker-extra-必須128) / [`SECURITY.md`](../../SECURITY.md)
