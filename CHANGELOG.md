# 変更履歴 / Changelog

本ファイルは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従い、
バージョニングは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従います。

## [Unreleased]

post-0.1.0 の改善（次のマイナーリリースに含める想定）。

### Added

- **`VaultStrategy`**: `MaskStrategy` プロトコルの実装として `Vault` を吸収する戦略を導入。`Masker(vault=...)` 指定時は内部で自動的に組み立てられ、戦略経路が単一化される。直接 import 可能（`from fuseji import VaultStrategy`）
- **`FusejiError` 例外階層**: `FusejiError`（基底）と `InvalidEntityError` / `InvalidConfigError`。多重継承で `ValueError` も継承するため `except ValueError` の既存コードは変更不要
- **公開 API の docstring に Example セクション** を追加（`Masker.mask` / `detect` / `mask_json`、`Placeholder` / `Redact` / `Hash`、`InMemoryVault`、`make_mask_fn`）。doctest として実行可能
- **`Masker(max_json_depth=...)`** で `mask_json` の再帰深度上限を制御可能（既定 100）。超過時は fail-closed で `"[fuseji: too deep]"` に置換
- **`fuseji.server.app.create_app(masker=..., max_body_bytes=...)`** factory を導入。カスタム認識器・Vault・NER を統合した Masker をサーバーに注入可能
- **FastAPI サーバーに `BodySizeLimitMiddleware`**: Content-Length が上限（既定 1MB、`FUSEJI_SERVER_MAX_BODY_BYTES` で上書き可）を超える要求を 413 で拒否
- **fuseji-bench**: `pytest-benchmark` 基盤と 23 ベンチケース（masker / replace_spans / recognizers / vault）。`tests/bench/` 配下。CI に bench ジョブを追加（informational）
- **レイテンシ回帰検知テスト** `tests/test_latency_regression.py`: 通常 pytest で実行され、O(n²) バグ等の性能回帰を即時 fail させる
- **認識器の共通ヘルパ** `recognizers/base.py` に `SEPARATOR_PATTERN` と `has_digit_boundary()` を抽出
- **テスト共通ヘルパ** `tests/conftest.py` で `make_entity` を集約（旧 `_entity` のヘルパ重複を解消）
- **`fuseji.entity_types` 定数モジュール**: `EMAIL` / `CREDIT_CARD` / `MY_NUMBER` / `JP_PHONE_NUMBER` / `JP_POSTAL_CODE` / `PERSON` を str 定数として提供。`V0_1_TYPES` frozenset も。`from fuseji import entity_types` または `from fuseji.entity_types import MY_NUMBER`。内部実装でも単一ソース化済み
- **`InMemoryVault.clear()`**: 全 placeholder マッピングと番号カウンタを破棄。`excluded_types` 設定は維持。`threading.Lock` で保護。長時間稼働サーバーでのメモリ解放、テストでの状態リセットに有用
- **Python 3.14 サポート** を classifier と CI test-core マトリクスに追加（test-extras は spaCy 3.8 の wheel 制約で 3.13 まで）
- **VaultStrategy 単体テスト**: `Masker` を介さない直接利用のテストを追加

### Changed

- **`Masker(vault=..., strategy=...)` 同時指定で UserWarning** を発行。これまで docstring に「vault 優先」と明記しつつ silent に受け入れていたため、ランタイムで設定ミスに気付けるようにする。挙動は変わらず vault 優先のまま

- **`InMemoryVault.assign`** を `threading.Lock` で保護（double-checked locking パターン）。Uvicorn の thread pool 経由でも並行採番衝突なし
- **Langfuse adapter のログ出力**: デフォルトで例外型名のみ（traceback なし）。トレースバック中の PII 漏洩を防ぐ。デバッグ用 escape hatch として `FUSEJI_LANGFUSE_LOG_TRACEBACK=1` 環境変数で従来の `logger.exception` 動作に戻せる

### Documentation

- **examples/**: Langfuse SDK / ingestion callback / OTel / GiNZA の 4 種類のサンプル
- **docs/design.md / docs/api.md**: 設計ドキュメントの公開部分と API リファレンス
- **SECURITY.md** を v0.1.x の追加機構で更新（traceback 除去、depth/body 制限、Vault.clear、thread-safety、FusejiError 階層）

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
