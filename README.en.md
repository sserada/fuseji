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

### v0.3 (shipped)

- `JP_ADDRESS` (47 prefectures + ward + banchi regex, minimum viable, opt-in)
- `CORPORATE_NUMBER` (13-digit, official checksum, opt-in)

### v0.4+ (candidate)

- `BANK_ACCOUNT_JP`, `DRIVERS_LICENSE_JP`
- NER backend comparison (GiNZA vs BERT-NER vs GLiNER-ja)
- High-precision `JP_ADDRESS` (jageocoder / normalize-japanese-addresses)

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

# MY_NUMBER and CREDIT_CARD are excluded by default
# (Number Act + PCI DSS alignment, non-restorable)
vault = InMemoryVault()
masker = Masker(vault=vault)

r1 = masker.mask("田中さんと佐藤さん")
# e.g. "<PERSON_1_a3f9b2c4>さんと<PERSON_2_a3f9b2c4>さん" (GiNZA enabled)

# Restore from LLM response (which contains r1.text)
restored = vault.restore(r1.text)
# 田中さんと佐藤さん

# Placeholders carry a Vault-instance-specific nonce (introduced in v0.2).
# `restore` only matches placeholders bearing this Vault's own nonce, so
# placeholders from a different Vault instance are passed through unchanged
# — structurally preventing cross-tenant leakage.
```

### Masking strategies

```python
from fuseji import Masker, Placeholder, Redact, Hash

Masker(strategy=Placeholder())                       # <EMAIL_1> (default)
Masker(strategy=Redact())                            # [REDACTED]
Masker(strategy=Hash())                              # 16-char SHA256 (v0.2 default; rainbow-resistant)
Masker(strategy=Hash(length=8, keep_mapping=True))   # v0.1-compat: 8 chars + reverse mapping
```

With the `[faker]` extra installed, `FakerStrategy` substitutes PII with format-preserving fakes:

```python
from fuseji import Masker
from fuseji.faker_strategy import FakerStrategy  # pip install 'fuseji[faker]'

masker = Masker(strategy=FakerStrategy(salt="my-app-salt"))
result = masker.mask("田中さん a@b.com")
# e.g. '林 陽子さん user@example.org' — formats preserved
# MY_NUMBER / CREDIT_CARD / CORPORATE_NUMBER fall back to <MASKED>
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

### Operational limits and authentication

| Limit | Default | Env var / API | On overflow |
| --- | --- | --- | --- |
| Request body size | 1 MB | `FUSEJI_SERVER_MAX_BODY_BYTES` / `create_app(max_body_bytes=...)` | HTTP 413 |
| Per-request processing time | 30 s | `FUSEJI_SERVER_TIMEOUT_SECONDS` / `create_app(timeout_seconds=...)` | HTTP 504 |
| `mask_json` recursion depth | 100 | `Masker(max_json_depth=...)` | fail-closed with `"[fuseji: too deep]"` |
| API key authentication | disabled | `FUSEJI_API_KEY` / `create_app(api_key=...)` | HTTP 401 on mismatch |
| CORS allowed origins | disabled | `FUSEJI_CORS_ORIGINS` (CSV) / `create_app(cors_origins=...)` | unlisted origins get no ACAO header |

> ⚠️ **For internet-exposed deployments**, always set both `FUSEJI_API_KEY` and `FUSEJI_CORS_ORIGINS`. The server is designed as a trusted-boundary sidecar.

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

- **v0.1** (shipped to PyPI): regex/checksum recognizers, GiNZA PERSON, Placeholder/Redact/Hash, Vault, Langfuse adapter, FastAPI server, CI
- **v0.2** (dev complete, next release): expanded Recognizer protocol (`name` + `regex_analyze` factory), security hardening (Vault placeholder nonce / Hash mapping opt-in / CC excluded by default / API-key auth + CORS / pure-ASGI chunked-body limit / opt-in mask_json dict-key masking), perf improvements (one-shot `normalize` / `assign_many` bulk / `_resolve_overlaps` early-exit / opt-in Hash LRU), quality (doctest + 90% coverage gate / Unicode coverage / cross-recognizer regression / bench expansion)
- **v0.3** (shipped, next release): `JP_ADDRESS` / `CORPORATE_NUMBER` recognizers (opt-in), `FakerStrategy` (`[faker]` extra), OTel SDK integration example, Docker image refresh
- **v0.4+** (candidate): NER backend comparison (BERT-NER / GLiNER-ja fine-tune), structured-field-aware masking, batch API, true sweep-line `_resolve_overlaps`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). New recognizers are first-class — just satisfy the `Recognizer` protocol with tests.

## License

Apache-2.0 — see [LICENSE](LICENSE).
