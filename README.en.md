# fuseji

**Japanese-first PII detection and masking middleware for LLM observability pipelines.**

[![CI](https://github.com/sserada/fuseji/actions/workflows/ci.yml/badge.svg)](https://github.com/sserada/fuseji/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

English | [日本語](README.md)

---

## Why fuseji

LLM observability platforms (Langfuse, LangSmith, Phoenix, OTel-based stacks) provide hooks for masking sensitive data before traces leave the application. But every reference implementation is English-centric: US phone numbers, SSNs, Latin-script names.

For Japanese text, existing solutions fail structurally:

| Tool | Japanese | My Number | JP phone |
| --- | --- | --- | --- |
| Presidio | ✗ (no recognizers shipped) | ✗ | ✗ (incidental matches only) |
| LLM Guard | ✗ (English BERT) | ✗ | ✗ |
| GLiNER PII | ✗ (six European langs) | ✗ | ✗ |
| OTel Collector | ✗ (regex only) | ✗ | ✗ |
| **fuseji** | **✓** | **✓** (Number Act compliant) | **✓** |

fuseji addresses Japanese-specific challenges: no whitespace word boundaries, large-to-small address ordering, full/half-width digit and hyphen variation, name-vs-common-noun ambiguity, and the 12-digit My Number structure.

## Entity coverage

### v0.1 (launch)

| Entity | Method | Notes |
| --- | --- | --- |
| `MY_NUMBER` | Regex + check digit | 12 digits, public spec, full/half-width tolerant, recall-biased |
| `JP_PHONE_NUMBER` | Regex + numbering-plan validation | Mobile 070/080/090, 0120, 0570, landline |
| `JP_POSTAL_CODE` | Regex + context boost | `〒` and `XXX-XXXX` forms, context words boost score |
| `EMAIL` | Regex | RFC-lite |
| `CREDIT_CARD` | Regex + Luhn | Locale-independent |
| `PERSON` | NER (GiNZA backend, `[ginza]` extra) | CPU: ~100ms / ~100 tokens |

### v0.2+

- `JP_ADDRESS` (normalization-first detection)
- `CORPORATE_NUMBER` (opt-in)
- `BANK_ACCOUNT_JP`, `DRIVERS_LICENSE_JP`
- NER backend comparison (GiNZA vs BERT-NER vs GLiNER-ja)

## Installation

```bash
# Regex core only (zero deps)
pip install fuseji

# Enable GiNZA PERSON detection
pip install 'fuseji[ginza]'

# Enable FastAPI server (/mask /detect /healthz)
pip install 'fuseji[server]'

# Everything
pip install 'fuseji[all]'
```

## Quickstart

```python
from fuseji import Masker

masker = Masker()

result = masker.mask("山田さん(連絡先: 090-1234-5678, taro@example.co.jp、〒123-4567)")

print(result.text)
# 山田さん(連絡先: <JP_PHONE_NUMBER_1>, <EMAIL_1>、<JP_POSTAL_CODE_1>)

for e in result.entities:
    print(e.type, e.text, e.score)
```

### Pseudonymization vault (reversible masking)

```python
from fuseji import Masker, InMemoryVault

vault = InMemoryVault()  # MY_NUMBER is excluded by default (Number Act compliance)
masker = Masker(vault=vault)

r1 = masker.mask("田中さんと佐藤さん")  # placeholders assigned
restored = vault.restore("<PERSON_1>さんへ返信しました")
# 田中さんへ返信しました
```

### Masking strategies

```python
from fuseji import Masker, Placeholder, Redact, Hash

Masker(strategy=Placeholder())  # <EMAIL_1> (default)
Masker(strategy=Redact())       # [REDACTED]
Masker(strategy=Hash(length=8)) # SHA256 hex prefix
```

## Langfuse SDK integration

```python
from langfuse import Langfuse
from fuseji.integrations.langfuse import make_mask_fn

langfuse = Langfuse(mask=make_mask_fn())
```

Exceptions are handled **fail-closed**: a fixed placeholder string is returned instead of the original data — never leaking PII even on failure.

## Server mode (Langfuse ingestion callback / OTel sidecar)

```bash
pip install 'fuseji[server]'
uvicorn fuseji.server.app:app --host 0.0.0.0 --port 8000
```

```bash
curl -X POST http://localhost:8000/mask \
  -H 'Content-Type: application/json' \
  -d '{"data": "メール: taro@example.com"}'
# {"data": "メール: <EMAIL_1>"}
```

OpenAPI: `http://localhost:8000/openapi.json`

### Operational limits

| Limit | Default | Env var / API | On overflow |
| --- | --- | --- | --- |
| Request body size | 1 MB | `FUSEJI_SERVER_MAX_BODY_BYTES` / `create_app(max_body_bytes=...)` | HTTP 413 |
| Per-request processing time | 30 s | `FUSEJI_SERVER_TIMEOUT_SECONDS` / `create_app(timeout_seconds=...)` | HTTP 504 |
| `mask_json` recursion depth | 100 | `Masker(max_json_depth=...)` | fail-closed with `"[fuseji: too deep]"` |

## Security and legal notes

fuseji follows **detect, never retain**:

- Detected values live in memory only and are never persisted
- `InMemoryVault` is session-scoped (process memory). Any persistence is the caller's responsibility
- **My Number is excluded from the vault by default** and cannot be restored (Number Act compliance)
- The Langfuse adapter is fail-closed: exceptions never leak original data

See [SECURITY.md](SECURITY.md) for details.

> ⚠️ fuseji performs **in-flight masking only**. Retention and logging of detected values are the caller's responsibility.

## Design and non-goals

See [docs/design.md](docs/design.md). v0.x non-goals: prompt-injection guardrails, image/PDF redaction, reversible encryption, streaming token-by-token masking, non-Japanese natural text (ASCII patterns are supported).

## Roadmap

- **v0.1** (current): regex/checksum recognizers, GiNZA PERSON, Placeholder/Redact/Hash, Vault, Langfuse adapter, FastAPI server, CI
- **v0.2**: `JP_ADDRESS`, Docker image for ingestion callback, OTel example, Faker strategy, fuseji-bench
- **v0.3**: NER backend comparison, structured-field-aware masking, batch API

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New recognizers are first-class — just satisfy the `Recognizer` protocol with tests.

## License

Apache-2.0 — see [LICENSE](LICENSE).
