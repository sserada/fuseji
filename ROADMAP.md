# ロードマップ / Roadmap

[日本語](#日本語) | [English](#english)

直近の変更は [CHANGELOG.md](CHANGELOG.md) を参照してください。詳細な設計議論は [docs/design.md §10](docs/design.md#10-ロードマップ) にあります。

---

## 日本語

### 短期: v0.3（開発中、リリース予定）

- **opt-in 認識器**: `JP_ADDRESS` (#127) / `CORPORATE_NUMBER` (#126)（実装済み）
- **`FakerStrategy`**: `[faker]` extra、ja_JP ロケールで PII を架空値に置換（実装済み、#128）
- **OpenTelemetry SDK 統合**: `fuseji.integrations.otel` 公式化（実装済み、#161）
- **Presidio 統合**: `fuseji.integrations.presidio` で Presidio の `EntityRecognizer` として登録可能に（実装済み、#147）
- **セキュリティ強化**: `/detect` のデフォルト PII redact (#143) / `Entity.__repr__` PII safe (#144) / `FakerStrategy` のデフォルト salt ランダム化 (#145) / `FakerStrategy.keep_mapping` opt-in 化 (#139)
- **CI/CD 強化**: pytest-randomly でテスト順序依存を検知 (#169) / GitHub Actions の SHA pin (#167) / FastAPI lifespan ウォームアップ (#173)

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

- **Opt-in recognizers**: `JP_ADDRESS` (#127) / `CORPORATE_NUMBER` (#126) (shipped)
- **`FakerStrategy`**: `[faker]` extra, ja_JP locale fictitious-value replacement (shipped, #128)
- **OpenTelemetry SDK integration**: `fuseji.integrations.otel` promoted to official module (shipped, #161)
- **Presidio integration**: register as Presidio `EntityRecognizer` (shipped, #147)
- **Security hardening**: default PII redact in `/detect` (#143), PII-safe `Entity.__repr__` (#144), randomized default `FakerStrategy` salt (#145), opt-in `keep_mapping` (#139)
- **CI/CD hardening**: pytest-randomly (#169), GitHub Actions SHA pinning (#167), FastAPI lifespan warm-up (#173)

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
