# カスタム Recognizer サンプル (#197)

自社専用 ID (社員番号 / 案件番号 / 端末 ID 等) を fuseji の `Recognizer` Protocol で実装し、既存の `default_recognizers()` と組み合わせて `Masker` に組み込む最小例。

## なぜカスタム認識器が必要か

fuseji の組み込み認識器 (`MY_NUMBER` / `JP_PHONE_NUMBER` / `JP_POSTAL_CODE` / `EMAIL` / `CREDIT_CARD` + opt-in の `JP_ADDRESS` / `CORPORATE_NUMBER`) は汎用的な日本語 PII を扱うが、企業固有の識別子は対象外。例:

- 社員番号 (`EMP-XXXXXX`)
- 案件 ID (`PROJ-2026-XXXXX`)
- 端末識別子 / 顧客番号 / 契約番号

これらは利用者側でカスタム認識器を実装して `Masker(recognizers=[...])` に渡すのが想定経路。

## 実装の最小単位

`Recognizer` Protocol を満たすには 3 つだけ必要:

| 属性 / メソッド | 型 / シグネチャ |
| --- | --- |
| `entity_type` | `str` (例: `"EMPLOYEE_ID"`) |
| `name` | `str` (snake_case 識別子、`Entity.recognizer` に格納) |
| `analyze(text, *, normalized=None)` | `Iterator[Entity]` |

`regex_analyze` ヘルパを使うと、オフセット計算 / Entity 構築 / 数字 boundary 判定 / `normalized` kwarg 対応のボイラープレートを大幅に削減できる。

## セットアップ

```bash
cd examples/custom_recognizer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 実行

```bash
python main.py
```

期待出力:

```
EMPLOYEE_ID  EMP-123456           score=0.9 recognizer=employee_id
EMAIL        taro@example.com     score=1.0 recognizer=email
EMPLOYEE_ID  EMP-100000           score=0.5 recognizer=employee_id
```

## 設計ポイント

1. **score の階層化**: 検証 OK は 0.9、形式は合うが検証 NG は 0.5 (recall 優先で残す)。`MyNumberRecognizer` / `CorporateNumberRecognizer` と同じ方針
2. **`normalized` kwarg**: Masker 層で 1 度だけ計算した `normalize(text)` を再利用するための慣用。`regex_analyze` ヘルパが自動で扱う
3. **digit boundary**: 周辺が数字の場合に別 ID の一部としてマッチさせないには `require_digit_boundary=True` を `regex_analyze` に渡す (EMP- prefix で区切れる本例では不要)
4. **`entity_type` の命名**: Presidio との integrate を想定するなら `JP_*` 接頭辞 (例: `JP_EMPLOYEE_ID`) で名前空間衝突を避ける

## 関連

- [`docs/api.md`](../../docs/api.md#recognizer-protocol) — Protocol の正式定義
- [`docs/design.md` §3.2](../../docs/design.md) — Recognizer 設計
- ビルトイン認識器の実装例: [`src/fuseji/recognizers/my_number.py`](../../src/fuseji/recognizers/my_number.py)
