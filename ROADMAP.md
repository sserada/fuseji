# ロードマップ / Roadmap

[日本語](#日本語) | [English](#english)

直近の変更は [CHANGELOG.md](CHANGELOG.md) を参照してください。詳細な設計議論は [docs/design.md §10](docs/design.md#10-ロードマップ) にあります。

---

## 日本語

### 短期: v0.3（開発中、リリース予定）

**新機能 / 統合**:

- `JP_ADDRESS` (#127) / `CORPORATE_NUMBER` (#126) opt-in 認識器
- `FakerStrategy` (`[faker]` extra、ja_JP、#128) — 運用ガイドは [`docs/integrations/faker.md`](docs/integrations/faker.md)
- OpenTelemetry SDK 公式統合 (`[otel]` extra、#161) — [`docs/integrations/otel.md`](docs/integrations/otel.md)
- Presidio 公式アダプタ (`[presidio]` extra、#147) — [`docs/integrations/presidio.md`](docs/integrations/presidio.md)

**セキュリティ強化**:

- `Entity` / `MaskResult` の `__repr__` を PII safe 化 (#144)
- `/detect` のデフォルト PII redact (#143)
- `FakerStrategy` デフォルト salt ランダム化 (#145) / `keep_mapping` opt-in (#139)
- `InMemoryVault` nonce を 32-bit → 128-bit に拡張 (#185)
- `[server]` extra に `starlette>=0.40,<2.0` 直接ピン (#189)
- GitHub Actions の SHA pin (#167)

**品質強化**:

- Hypothesis property-based テスト導入 (#183)
- pytest-randomly でテスト順序依存検知 (#169)
- `CorporateNumberRecognizer` 複数件テストで score の明示 assert (#179)
- `examples/otel` スモークテスト (#171)

**パフォーマンス改善**:

- FastAPI lifespan で Masker ウォームアップ (#173)
- `FakerStrategy._faker_cache` LRU bound (#177)
- `FakerStrategy._build_faker` インスタンス使い回し (#142)
- `Placeholder.mask` ループ融合 + `_replace_spans` `pre_sorted` (#187)
- `JpAddressRecognizer` の regex バックトラック対策 (#141) / 後続 greedy 抑制 (#140)
- worst-case bench シナリオ追加 (`mask_json` wide-and-deep / 全 entity 重複 / unique surfaces) (#181)

**コミュニティ・ドキュメント**:

- `CODE_OF_CONDUCT.md` / `SUPPORT.md` / `ROADMAP.md` 整備 (#175)
- README 比較表に汎用 LLM ベース redactor (OpenAI Privacy Filter / GLiNER2-PII) を追加 (#146)
- 日英 README に OTel / Presidio 統合セクション (#163)

### 中期: v0.4 候補

- **NER バックエンド比較**: GiNZA vs BERT-NER vs GLiNER-ja fine-tune の F1 / レイテンシ評価
- **構造化フィールド対応**: JSON キー保持・JSONPath ベースの除外規則
- **batch API**: span processor 向けの一括マスキング API
- **true sweep-line `_resolve_overlaps`**: worst-case `O(n log n)` 化（現状は near-linear）
- **`BANK_ACCOUNT_JP` / `DRIVERS_LICENSE_JP`**: 追加日本語認識器（公開仕様の有無で検討）
- **`JP_ADDRESS` 高精度版**: jageocoder / normalize-japanese-addresses 系の評価と組み込み

### 長期: v1.0+

- **Presidio 本体への upstream**: Japan recognizer pack として upstream PR
- **LLM Guard backend 連携**
- **バイリンガル docs サイト**: MkDocs / mdBook ベース
- **Docker / SBOM / Helm Chart**: コンテナ運用向け配布形態（v0.4+ で着手予定）

### 議論したい題材

実装方針が確定していない題材は [GitHub Discussions](https://github.com/sserada/fuseji/discussions) で扱います。フィードバック歓迎です。

---

## English

### Near-term: v0.3 (in development)

**New features / integrations**:

- Opt-in recognizers `JP_ADDRESS` (#127) / `CORPORATE_NUMBER` (#126)
- `FakerStrategy` (`[faker]` extra, ja_JP, #128) — operations guide: [`docs/integrations/faker.md`](docs/integrations/faker.md)
- Official OpenTelemetry SDK integration (`[otel]` extra, #161) — [`docs/integrations/otel.md`](docs/integrations/otel.md)
- Official Presidio adapter (`[presidio]` extra, #147) — [`docs/integrations/presidio.md`](docs/integrations/presidio.md)

**Security hardening**:

- PII-safe `__repr__` for `Entity` / `MaskResult` (#144)
- Default redact of PII in `/detect` (#143)
- Randomized default `FakerStrategy` salt (#145) / opt-in `keep_mapping` (#139)
- `InMemoryVault` nonce widened from 32-bit to 128-bit (#185)
- Explicit `starlette>=0.40,<2.0` pin in `[server]` extra (#189)
- GitHub Actions SHA pinning (#167)

**Quality hardening**:

- Hypothesis property-based testing (#183)
- pytest-randomly to surface ordering dependencies (#169)
- Explicit score asserts in CorporateNumber multi-entity test (#179)
- `examples/otel` smoke test (#171)

**Performance improvements**:

- FastAPI lifespan warm-up of Masker (#173)
- `FakerStrategy._faker_cache` LRU bound (#177)
- `FakerStrategy._build_faker` instance reuse (#142)
- `Placeholder.mask` loop fusion + `_replace_spans` `pre_sorted` (#187)
- `JpAddressRecognizer` regex backtracking guard (#141) / trailing-greedy fix (#140)
- Worst-case bench scenarios (wide-and-deep `mask_json` / full-overlap / unique surfaces) (#181)

**Community / docs**:

- `CODE_OF_CONDUCT.md` / `SUPPORT.md` / `ROADMAP.md` (#175)
- Comparison table updated with general-purpose LLM-based redactors (OpenAI Privacy Filter / GLiNER2-PII) (#146)
- OTel / Presidio integration sections mirrored to English README (#163)

### Medium-term: v0.4 candidates

- **NER backend comparison**: GiNZA vs BERT-NER vs GLiNER-ja fine-tune (F1 / latency)
- **Structured field handling**: JSON key preservation, JSONPath-based exclusion rules
- **Batch API**: bulk masking for span processors
- **True sweep-line `_resolve_overlaps`**: worst-case `O(n log n)` (currently near-linear)
- **`BANK_ACCOUNT_JP` / `DRIVERS_LICENSE_JP`**: additional Japanese recognizers (pending public-spec evaluation)
- **High-precision `JP_ADDRESS`**: integrate jageocoder / normalize-japanese-addresses families

### Long-term: v1.0+

- **Upstream to Presidio**: contribute Japan recognizer pack
- **LLM Guard backend integration**
- **Bilingual docs site**: MkDocs / mdBook
- **Docker / SBOM / Helm Chart**: container distribution (planned in v0.4+)

### Topics under discussion

Items whose direction is not yet fixed are tracked in [GitHub Discussions](https://github.com/sserada/fuseji/discussions). Feedback welcome.
