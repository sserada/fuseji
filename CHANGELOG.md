# 変更履歴 / Changelog

本ファイルは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従い、
バージョニングは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従います。

## [Unreleased]

## [0.1.0] - 2026-06-11

初回リリース。日本語特化の PII 検出・マスキングミドルウェア。

### Added

- **コア型**: `Entity`、`MaskResult`（frozen dataclass、バリデーション付き）
- **マスキング戦略**: `MaskStrategy` プロトコル + `Placeholder` / `Redact` / `Hash` の 3 実装
- **仮名化バウルト**: `Vault` プロトコル + `InMemoryVault` 実装。同一 (type, surface) → 同一 placeholder、`MY_NUMBER` をデフォルト除外（番号法対応）。restore は placeholder regex マッチで安全化
- **PII 認識器（v0.1 セット）**:
  - `EMAIL`（RFC-lite）
  - `CREDIT_CARD`（Luhn 検証）
  - `MY_NUMBER`（12 桁、総務省公開仕様のチェックディジット、recall 優先）
  - `JP_PHONE_NUMBER`（携帯 070/080/090、フリーダイヤル 0120、ナビダイヤル 0570、固定電話）
  - `JP_POSTAL_CODE`（〒、コンテキストブースト）
  - すべて全角数字・全角ハイフン対応
- **NER バックエンド**: `NerBackend` プロトコル + GiNZA 実装（`[ginza]` extra）で PERSON 検出
- **Masker エンジン**: `Masker.mask` / `Masker.mask_json` / `Masker.detect`。オーバーラップ解決はスコア優先 → 長 span 優先 → 開始位置順
- **Langfuse SDK アダプタ**: `make_mask_fn()`。fail-closed 設計（例外時は `[fuseji: masking failed]` を返却）
- **FastAPI サーバー**: `[server]` extra として `POST /mask`、`POST /detect`、`GET /healthz`、OpenAPI 自動生成
- **CI**: GitHub Actions で lint / mypy / pytest を Python 3.10–3.13 マトリクス + 全 extras ジョブ
- **ドキュメント**: README（日本語メイン + 英語ミラー）、SECURITY.md（番号法対応明記）、CONTRIBUTING.md

### Performance

- `_replace_spans` を list-of-segments の 1 パスに変更し O(n²) → O(n+k)
- `normalize()` の translate テーブルを統合し 2 パスから 1 パスに

### Security

- `InMemoryVault.restore()` を placeholder regex マッチに変更し silent corruption を排除
- マイナンバーは Vault のデフォルト除外集合に含み、復元不可

[Unreleased]: https://github.com/sserada/fuseji/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sserada/fuseji/releases/tag/v0.1.0
