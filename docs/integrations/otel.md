# OpenTelemetry SDK 統合 (`fuseji.integrations.otel`)

OpenTelemetry SDK の span 属性をマスクするためのヘルパ (#161)。

OTel の `SpanProcessor.on_end` は `ReadableSpan` を受け取るが、`ReadableSpan` には `set_attribute` が存在せず属性 mutation はできない。属性 mutation には内部 `_attributes` (`BoundedAttributes`) を private API として叩く必要があり、SDK バージョンアップで壊れる脆い経路となる。

本モジュールは「**属性を set する前にマスクする**」明示的なヘルパを提供する。OTel SDK のどのバージョンでも動作し、ベンダーロックインもない。

## インストール

```bash
pip install 'fuseji[otel]'
```

`[otel]` extra は `opentelemetry-api>=1.20` を引きます。`opentelemetry-sdk` 本体は利用者のアプリ側でインストールしてください。

## API

### `mask_attribute(span, key, value, masker=None)`

`span.set_attribute(key, value)` を呼ぶ前に value をマスクします。`value` が `str` 以外（`int` / `bool` / `Sequence` 等）はそのまま set されます。

```python
from opentelemetry import trace
from fuseji import Masker
from fuseji.integrations.otel import mask_attribute

masker = Masker()
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("llm-call") as span:
    mask_attribute(span, "gen_ai.prompt", user_prompt, masker)
```

### `mask_attributes(span, attributes, masker=None, keys=None)`

複数属性を一括で set します。`keys=` でマスク対象キーを絞れます（デフォルト: `DEFAULT_ATTRIBUTE_KEYS`）。

```python
from fuseji.integrations.otel import mask_attributes

mask_attributes(
    span,
    {
        "gen_ai.prompt": "メール taro@example.com",
        "model": "gpt-5",  # keys に含まれないため素通し
    },
    masker,
)
```

`keys=()` (空 tuple) は「フィルタなし」として、すべての文字列属性をマスク対象にします。

### `DEFAULT_ATTRIBUTE_KEYS`

GenAI semantic conventions と派生命名を網羅:

```python
("gen_ai.prompt", "gen_ai.completion", "gen_ai.request.messages",
 "gen_ai.response.text", "llm.prompts", "llm.completions",
 "input.value", "output.value")
```

Langfuse / Phoenix / OpenInference / OpenLIT が採用する命名を含みます。利用者は `mask_attributes(..., keys=...)` で上書き可能。

## fail-closed (#222)

`Masker.mask` が任意の例外（regex catastrophic / カスタム recognizer のバグ等）で失敗した場合、`mask_attribute` / `mask_attributes` は **固定 placeholder `"[fuseji: masking failed]"`** を `set_attribute` し、原 value を span に流出させません。Langfuse adapter と方針を統一しています（`fuseji.integrations.langfuse.make_mask_fn` 参照）。

`mask_attributes` は属性ごとに独立した try/except を持つため、ある属性のマスク失敗が他属性の処理を止めません。

### ログ抑制とトレースバック opt-in

トレースバックには原 PII を含む文字列が刻まれる可能性があるため、デフォルトでは **例外型名のみ** ログ出力します（`logger.warning`）。詳細 traceback が必要なデバッグ局面のみ環境変数を有効にしてください:

```bash
export FUSEJI_OTEL_LOG_TRACEBACK=1
```

有効化時は `logger.exception` で完全な traceback を出力します。Langfuse adapter の `FUSEJI_LANGFUSE_LOG_TRACEBACK` と方針を統一しています。

## 設計上の注意

- `mask_attribute(masker=None)` は内部で新規 `Masker()` を生成しますが、毎回ゼロから作るとレイテンシ予算を浪費します。**呼び出し側で 1 つだけ作って使い回す**ことを強く推奨します
- 既存の OTel Collector の `transform` processor (regex のみ) ではなく SDK 統合を推奨する経路です。Collector 経路では人名・住所のような自然文 PII を扱えません
- 例: `examples/otel/main.py` 参照
