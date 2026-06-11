# 変更履歴 / Changelog

本ファイルは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従い、
バージョニングは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従います。

## [Unreleased]

### Added

- `Recognizer` プロトコルに `name` 属性（snake_case 識別子、`Entity.recognizer` に格納）を追加
- `fuseji.recognizers.base.regex_analyze` — regex + 検証関数の共通テンプレート関数を公開。
  カスタム認識器の追加でボイラープレートを大幅に削減できる（#45）

### Changed

- ビルトイン認識器（`email` / `credit_card` / `my_number` / `jp_phone`）を
  `regex_analyze` ベースに再実装。挙動・スコアは v0.1.0 と完全互換（#45）

## [0.1.0] - 2026-06-12

初回 PyPI リリース。日本語特化の PII 検出・マスキングミドルウェア。

### Added

#### コア機能

- **コア型**: `Entity`、`MaskResult`（frozen dataclass、バリデーション付き）
- **マスキング戦略**: `MaskStrategy` プロトコル + `Placeholder` / `Redact` / `Hash` / `VaultStrategy` の 4 実装
- **仮名化バウルト**: `Vault` プロトコル + `InMemoryVault` 実装。同一 (type, surface) → 同一 placeholder、`MY_NUMBER` をデフォルト除外（番号法対応）
  - `restore()` は placeholder regex マッチで silent corruption を構造的に防ぐ
  - `clear()` で全マッピングを破棄可能（`excluded_types` 設定は維持）
  - `size` プロパティで登録済み placeholder 数を取得
  - `assign()` は `threading.Lock` で保護（並行採番衝突なし）
  - `__repr__` で状態を可視化
- **PII 認識器（v0.1 セット）**:
  - `EMAIL`（RFC-lite）
  - `CREDIT_CARD`（Luhn 検証）
  - `MY_NUMBER`（12 桁、総務省公開仕様のチェックディジット、recall 優先）
  - `JP_PHONE_NUMBER`（携帯 070/080/090、フリーダイヤル 0120、ナビダイヤル 0570、固定電話）
  - `JP_POSTAL_CODE`（〒、コンテキストブースト）
  - すべて全角数字・全角ハイフン対応、共通ヘルパ（`SEPARATOR_PATTERN`, `has_digit_boundary`）
- **NER バックエンド**: `NerBackend` プロトコル + GiNZA 実装（`[ginza]` extra）で PERSON 検出
- **Masker エンジン**:
  - `Masker.mask` / `Masker.mask_json` / `Masker.detect`
  - オーバーラップ解決はスコア優先 → 長 span 優先 → 開始位置順
  - `max_json_depth`（既定 100）で `mask_json` の再帰深度を制限、超過時は fail-closed
  - `Masker(vault=..., strategy=...)` 同時指定で `UserWarning`（vault 優先）

#### 統合

- **Langfuse SDK アダプタ**: `make_mask_fn()`。fail-closed 設計
  - 例外時は固定 placeholder `"[fuseji: masking failed]"` を返し原データを露出しない
  - デフォルトログは例外型名のみ（traceback 内 PII 漏洩防止）、`FUSEJI_LANGFUSE_LOG_TRACEBACK=1` で詳細出力
- **FastAPI サーバー**（`[server]` extra）:
  - `POST /mask` / `POST /detect` / `GET /healthz` / OpenAPI 自動生成
  - `create_app(masker=..., max_body_bytes=...)` factory で DI
  - `BodySizeLimitMiddleware` で 1MB 超リクエストを 413 で拒否（環境変数で上書き可）

#### API ユーティリティ

- **`fuseji.entity_types` 定数モジュール**: `EMAIL` / `CREDIT_CARD` / `MY_NUMBER` / `JP_PHONE_NUMBER` / `JP_POSTAL_CODE` / `PERSON` を str 定数として提供
- **`FusejiError` 例外階層**: `FusejiError`（基底）/ `InvalidEntityError` / `InvalidConfigError`。多重継承で `ValueError` も継承（後方互換）
- **公開 API の docstring に Example セクション**（doctest として実行可能）

#### 品質・運用

- **CI**: GitHub Actions で ruff / mypy / pytest を Python 3.10–3.14 マトリクス + 全 extras ジョブ + 情報的 bench ジョブ
- **fuseji-bench**: `pytest-benchmark` 基盤と 23 ベンチケース
- **レイテンシ回帰検知テスト**: O(n²) バグ等を通常 pytest で即時 fail（Masker 1KB/4KB、Vault.restore m=1000）
- **PyPI 公開**: Trusted Publishing (OIDC) workflow

### Performance

- `_replace_spans` を list-of-segments の 1 パスに変更し O(n²) → O(n+k)
- `normalize()` の translate テーブルを統合し 2 パスから 1 パスに

### Security

- マイナンバーは Vault のデフォルト除外集合に含み復元不可
- `InMemoryVault.restore()` を placeholder regex マッチに変更し silent corruption を構造的に排除
- `InMemoryVault.assign` を `threading.Lock` で保護
- Langfuse adapter のデフォルトログから traceback 除去
- `Masker(max_json_depth=...)` で DoS 対策
- `BodySizeLimitMiddleware` で巨大ペイロードを拒否

### Documentation

- README（日本語メイン + 英語ミラー）
- SECURITY.md（番号法対応・脆弱性報告窓口・設計上の安全保証）
- docs/design.md / docs/api.md
- examples/（Langfuse SDK / ingestion callback / OTel / GiNZA）
- CONTRIBUTING.md

[Unreleased]: https://github.com/sserada/fuseji/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sserada/fuseji/releases/tag/v0.1.0
