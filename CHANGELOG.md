# 変更履歴 / Changelog

本ファイルは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従い、
バージョニングは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従います。

## [Unreleased]

### Breaking Changes

- `Recognizer` プロトコルの `analyze` シグネチャが `analyze(self, text: str, *, normalized: str | None = None) -> Iterable[Entity]` に変更。`normalized` kwarg を受け取らないカスタム認識器は v0.2 以降で `TypeError` になる（#93）
  - Masker 内部の `inspect.signature` ベース dispatch（`_accepts_normalized_kwarg`）を廃止し、code path がシンプルに
  - 移行方法: 既存の `def analyze(self, text)` に `*, normalized=None` を追加するだけ。`normalized` を使わない認識器は引数を無視してよい
- `Hash` 戦略のセキュリティ既定値を強化（#82）:
  - デフォルト `length` を 8 → 16（64bit）に引き上げ。低エントロピー PII（email/電話番号）へのレインボー攻撃耐性を強化
  - デフォルト `keep_mapping` を **False** に設定。`Hash().mask(...)` の戻り値 `mapping` は空 dict
  - 逆引きが必要な場合は `Hash(keep_mapping=True)` を明示的に指定（v0.1 互換の挙動）
  - 移行方法: 既存コードで `mapping` を使っていた場合は `Hash(keep_mapping=True)` に書き換える。`length` を 8 固定にしていた場合は `Hash(length=8, keep_mapping=True)` でハッシュ値も維持できる
- `Masker.mask_json` の depth 境界仕様を明確化（#99）:
  - 比較を `depth > max_json_depth` → `depth >= max_json_depth` に変更
  - 新仕様: `max_json_depth=N` のとき、ルート(depth=0) を起点に 0..N-1 の **計 N 段** まで再帰を許容、depth N 以降で fail-closed
  - 旧仕様（v0.1）は off-by-one で実際は N+1 段まで処理されていた
  - 移行方法: `max_json_depth` を 1 段増やせば旧挙動を維持できる（例: `Masker(max_json_depth=100)` → `Masker(max_json_depth=101)`）
- `InMemoryVault.DEFAULT_EXCLUDED_TYPES` に `CREDIT_CARD` を追加（#84）:
  - PCI DSS Requirement 3.4 / 3.5 で「保存禁止または強い保護下」が求められる PAN を、番号法対応の `MY_NUMBER` と同等に Vault 復元不可とする
  - 結果: `Vault(masker=...)` 経路で CREDIT_CARD は `<CREDIT_CARD>`（番号なし）で固定マスクされ、`mapping` に残らない
  - 移行方法: 旧挙動を維持する場合は `InMemoryVault(excluded_types=["MY_NUMBER"])` を明示指定して CREDIT_CARD を除外集合から外す

### Added

- `Recognizer` プロトコルに `name` 属性（snake_case 識別子、`Entity.recognizer` に格納）を追加
- `fuseji.recognizers.base.regex_analyze` — regex + 検証関数の共通テンプレート関数を公開。
  カスタム認識器の追加でボイラープレートを大幅に削減できる（#45）
- ビルトイン認識器の `analyze` メソッドが `normalized: str | None = None` キーワード引数を
  受け取れるようになった。Masker 層で事前計算した正規化済みテキストを再利用可能（#24）

### Changed

- ビルトイン認識器（`email` / `credit_card` / `my_number` / `jp_phone`）を
  `regex_analyze` ベースに再実装。挙動・スコアは v0.1.0 と完全互換（#45）

### Performance

- `Masker.detect` が `normalize(text)` を 1 回だけ計算し、対応する認識器に
  事前正規化済みテキストを渡すよう改良。デフォルト 5 認識器構成で従来は
  4 回呼ばれていた `str.translate` フルスキャンが 1 回に削減される。
  カスタム認識器との後方互換性は `inspect.signature` ベースのオプトイン検出で確保（#24）

### Security

- `fuseji.server.app.RequestTimeoutMiddleware` を追加。/mask /detect エンドポイントの
  1 リクエストあたり処理時間に上限を設け、超過時は HTTP 504 を返す。デフォルト 30 秒、
  環境変数 `FUSEJI_SERVER_TIMEOUT_SECONDS` または `create_app(timeout_seconds=...)`
  で設定可能。長文 + 多数 entity による占有を防ぐ DoS 緩和策（#29）

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
