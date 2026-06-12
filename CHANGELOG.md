# 変更履歴 / Changelog

本ファイルは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従い、
バージョニングは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に従います。

## [Unreleased]

### Breaking Changes

- `Entity` と `MaskResult` の `__repr__` を PII safe に変更（#144、security fix）:
  - `repr(entity)` は `text='...'` ではなく `text=<len=N hash=XXXXXXXX>` 形式の安全要約を返す
  - `repr(result)` は `entities=<count=N>` / `mapping=<count=M>` のみで中身を出さない
  - `Entity.text` への属性参照は従来通り（API は変わらず）。`logger.info('%s', entity)` / pytest assert dump / FastAPI 500 traceback で原 PII が偶発的に刻まれるのを防ぐ
  - デバッグ用に `Entity.unsafe_repr()` を opt-in で別途用意。呼び出し元が PII 露出責任を負う
  - 移行方法: テストやログで `repr(entity)` の文字列に依存していた場合は `entity.unsafe_repr()` に書き換える、または `entity.text` を直接参照する
  - OWASP ASVS V7.1.1 / CWE-209 / CWE-532 対応
- `POST /detect` レスポンスから原 PII surface をデフォルト除去（#143、security fix）:
  - `DetectResponse.entities[].text` がデフォルトで `null` を返すよう変更（旧: 原 surface を平文で返却）
  - 「detect, never retain」原則 / OWASP LLM02:2025 / CWE-200 への対応。クライアントは原テキストを自身で保持しているため、`type`/`start`/`end`/`score`/`recognizer` のみで再構築できる
  - 原 surface が必要な用途は `create_app(detect_include_surface=True)` または環境変数 `FUSEJI_DETECT_INCLUDE_SURFACE=1` で opt-in
  - opt-in 時も `MY_NUMBER` / `CREDIT_CARD` / `CORPORATE_NUMBER` は `<redacted>` 固定（番号法対応 + PCI DSS）
  - 移行方法: クライアントが `text` フィールドに依存している場合は `detect_include_surface=True` を明示指定するか、`text` 利用箇所を削除する

### Added

- `FakerStrategy` の mapping を opt-in に変更（#139、security fix）:
  - `keep_mapping: bool = False` を追加。デフォルトで `MaskResult.mapping` を空 dict
  - v0.3 初期版で `fake → 原 PII` を mapping に保存していたが「detect, never retain」原則と矛盾していた経路を遮断
  - 旧挙動が必要な場合は `FakerStrategy(keep_mapping=True)` を明示指定
- `FakerStrategy` を追加 (`[faker]` extra、#128):
  - Faker で PII を架空値に置換する戦略。ja_JP ロケール
  - 高センシティビティ type (`MY_NUMBER` / `CREDIT_CARD` / `CORPORATE_NUMBER`) は再検出回避のため固定マスク `<MASKED>` で置換
  - `JP_PHONE_NUMBER` / `JP_POSTAL_CODE` は安全な fictitious format（`070-0000-XXXX` / `999-XXXX`）で再検出問題を回避
  - `EMAIL` は `safe_email` (RFC 6761 reserved domain)
  - 決定的モード (`deterministic=True` デフォルト): 同一 surface に同一 fake → マルチターンの context preservation
  - `from fuseji.faker_strategy import FakerStrategy` で利用
- `examples/otel` に OpenTelemetry SDK 統合サンプルを追加（#129）:
  - `mask_attribute(span, key, value, masker)` helper を提供。`set_attribute` 前に
    fuseji.Masker でマスクする明示パターン
  - SpanProcessor.on_end は `ReadableSpan` を受けて属性 mutation できないため、
    set 前マスクが最も portable と判断（Lambda hook / Sidecar transform / Python
    extension の 3 案のうち SDK 統合を採用）
  - 動作確認済み: `gen_ai.prompt` の PII が `<EMAIL_1>` 等に置換されてコンソール export
  - 既存 `otel-collector-config.yaml` は属性削除のフォールバック例として保持、SDK
    統合を推奨経路として README を再構成
- `FakerStrategy._build_faker` で Faker インスタンスを strategy あたり 1 回だけ構築するよう変更（#142、perf）:
  - 旧実装は `_fake_for` cache miss のたびに `Faker(self.locale)` を新規構築（locale provider ロードに数 ms〜十数 ms）
  - インスタンスを `_faker_holder` で持ち、`seed_instance(seed)` のみ surface 毎に差し替える形に変更（seed_instance は provider rebuild なし）
  - 100 unique surface で 43ms → 16ms（ローカル M1 計測、2.6x 改善）
  - 決定性 / cross-instance 等価性は維持
  - `tests/bench/bench_strategies.py::test_faker_strategy_cache_miss` で cache miss path を回帰検出
- `JpAddressRecognizer` の住所 regex に worst-case バックトラック対策（#141、security/perf）:
  - `_CITY_PATTERN` を `{1,20}` の bounded quantifier 化（実在市区町村名は最長級でも 10 文字程度）
  - attacker-controlled な長大漢字列（例: `'東京都' + '亜' * 16384`）に対する worst-case 線形性を担保
  - bench (`tests/bench/bench_v03_recognizers.py::test_jp_address_pathological`) と
    レイテンシ回帰テスト (`tests/test_latency_regression.py::TestJpAddressPathologicalLatency`) を追加
- `JpAddressRecognizer` の後続テキスト greedy 取り込みを抑制（#140、bug fix）:
  - place_name パターンを「番地（数字）が後続する場合のみ消費」に変更
  - 「東京都町田市無関係な続きテキスト」のように番地のない文で後続漢字を呑み込む問題を解消
  - スコアセマンティクス変更なし（番地なし → 0.5、番地あり → 0.7/0.9）
- `JpAddressRecognizer`（日本の住所、`JP_ADDRESS`、opt-in）を追加（#127、minimum viable）:
  - 47 都道府県 + 市区町村 + 任意の番地パターンを正規表現で検出
  - スコア: 番地 + コンテキスト語 (住所/在所/居住地) ありで 0.9、番地のみで 0.7、都道府県 + 市区町村のみで 0.5
  - 公開情報のため `default_recognizers()` には含めず明示的に組み込む
  - **既知制限**: 北海道の条記法、漢数字、マンション名、都道府県省略の住所は未対応。dictionary-based 高精度版は別 Issue で検討予定
- `CorporateNumberRecognizer`（法人番号、`CORPORATE_NUMBER`）を追加（#126）:
  - 国税庁公開仕様の 13 桁チェックディジット検証
  - `MY_NUMBER` と同じく recall 優先（不一致でも score 0.5 で残す）
  - 公開情報のため `default_recognizers()` には含めず opt-in
  - `Masker(recognizers=[*default_recognizers(), CorporateNumberRecognizer()])` で明示組み込み
  - `entity_types.CORPORATE_NUMBER` 定数追加
- `Vault` プロトコルに `assign_many(pairs)` を追加（#97）:
  - `(type, surface)` のシーケンスに対し一括で placeholder を割り当てる API
  - `InMemoryVault` 実装は 1 回の lock 取得で全件処理し、`VaultStrategy.mask` で k 回の lock contention を 1 回に縮約
  - `VaultStrategy.mask` をユニーク化 + `assign_many` ベースに書き換え
  - Protocol default 実装は個別 `assign` の繰り返しなので、サードパーティ Vault は破壊的変更なし
- `InMemoryVault(max_size=N)` オプションを追加（#86）:
  - 登録済み placeholder 数の上限を設け、上限到達後の新規 `assign` では FIFO で最古エントリを退避
  - 長時間稼働サーバーでメモリ使用量とメモリダンプ経由の事後流出リスクを抑止する DoS 緩和策
  - デフォルトは `None`（無制限、v0.1 互換）
  - 番号カウンタは維持され、退避済み placeholder 番号は再利用されない（restore 衝突防止）
- `Masker(mask_dict_keys=True)` オプションを追加（#85）:
  - `mask_json` で dict のキー（str のみ）も値と同じ戦略でマスクする
  - デフォルトは `False`（v0.1 互換、キーは素通し）
  - 動的キーに PII が入る LLM オブザーバビリティ用途で `True` を指定
  - キー衝突時は `__N` サフィックスで一意化（情報損失を防ぐ）

### Changed

- v0.3 認識器と FakerStrategy のベンチを追加（PR #137）:
  - `bench_v03_recognizers.py` 新設: `CorporateNumberRecognizer` / `JpAddressRecognizer` を 1KB / 4KB で計測
  - `bench_strategies.py` に `test_faker_strategy` 追加: cache hit パスの計測、faker 未インストール環境は skip
  - 計測例 (M1): CORPORATE_NUMBER 1KB ~27μs / 4KB ~109μs、JP_ADDRESS 1KB ~39μs / 4KB ~157μs（線形スケール、< 1ms/KB target 内）
- ベンチマークを 3 領域に拡充（#98）:
  - `bench_resolve_overlaps.py` を新設し、entity 数 10/100/1000 で `_resolve_overlaps` の O(n²) スケール曲線を計測（#95 sweep-line 化の前後比較に利用）
  - `bench_mask_json.py` を新設し、flat dict (100/1000 leaf) と入れ子 (3/10 段) の `mask_json` レイテンシを計測
  - `bench_strategies.py` を新設し、Placeholder / Redact / Hash / VaultStrategy を 100 PII で横並び比較（#96 #97 の前後計測に利用）
- ベンチマークの環境マーカーと CI 信頼性を改善（#92）:
  - `tests/bench/conftest.py` を追加し、`pytest_benchmark_update_machine_info` フックで `fuseji_env_key`（例: `darwin-arm64` / `linux-x86_64`）を machine_info に埋め込む。baseline ファイル名に環境キーを含める運用を `tests/bench/README.md` で案内
  - `tests/test_latency_regression.py` の閾値テストをデフォルトスキップに変更。`CI_PERF=1` を設定したジョブまたはローカル検証でのみ実行（通常 CI のノイズで偽陽性が起きやすかったため）
- 軽微なコード品質改善をまとめて反映（#94）:
  - `MaskResult.mapping` のデフォルト値を `MappingProxyType({})` のシングルトンに変更。`field(default_factory=dict)` で毎回 mutable dict を生成するコストを排除
  - `server/app.py` の env 変数パース処理を共通ヘルパ `_positive_from_env` に集約（`_max_body_bytes_from_env` / `_timeout_seconds_from_env` の重複を吸収）
  - `Recognizer.analyze` / `NerBackend.analyze` / GiNZA 実装の戻り型を `Iterable[Entity]` → `Iterator[Entity]` に統一。実体は generator なので「1 回しか走査できない」契約を型で表現
  - GiNZA バックエンドのラベルリテラル `"Person"` を `_GINZA_PERSON_LABEL` 定数に集約
  - `fuseji.recognizers.__all__` から内部ヘルパ (`regex_analyze`, `normalize_digits`, `normalize_hyphens`) を除外。必要なら `from fuseji.recognizers.base import ...` で個別 import

### Breaking Changes

- `Recognizer` プロトコルの `analyze` シグネチャが `analyze(self, text: str, *, normalized: str | None = None) -> Iterable[Entity]` に変更。`normalized` kwarg を受け取らないカスタム認識器は v0.2 以降で `TypeError` になる（#93）
  - Masker 内部の `inspect.signature` ベース dispatch（`_accepts_normalized_kwarg`）を廃止し、code path がシンプルに
  - 移行方法: 既存の `def analyze(self, text)` に `*, normalized=None` を追加するだけ。`normalized` を使わない認識器は引数を無視してよい
- `InMemoryVault` の placeholder にインスタンス固有 nonce を導入（#81）:
  - 形式が `<TYPE_N>` → `<TYPE_N_nonce>` に変更（v0.2 breaking）。`nonce` は 8 文字 hex (32bit) を `secrets.token_hex(4)` で自動生成
  - 別 Vault が生成した placeholder 形式の文字列を `restore` しても、nonce 不一致で素通しされる → クロステナント漏洩経路を構造的に遮断
  - テスト用途では `InMemoryVault(nonce="...")` で明示指定可能（再現性確保）
  - 移行方法: v0.1 の placeholder 形式に依存していたコードは `vault.nonce` プロパティ経由で動的に組み立てる
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

- `Hash(cache=True)` を追加し SHA256 digest をプロセス内 LRU (max 8192) で再利用可能に（#96、opt-in）:
  - 同一 PII surface が反復するログでは SHA256 計算が省ける
  - **セキュリティ注意**: LRU キーとして PII surface がプロセスメモリに保持される（最大 8192 件）。「detect, never retain」設計原則と背反するトレードオフがあるため、デフォルトは `cache=False`。明示的に `cache=True` を指定したときのみ有効化
  - LRU は `Hash` インスタンスをまたいで共有される（モジュール level）
- `_resolve_overlaps` に `max_end_so_far` 早期採用パスを追加（#95）:
  - 候補の `start` が採用済みの最大 `end` 以上のとき、線形スキャンせず O(1) で即採用
  - 完全に重ならない入力（典型的な fuseji 利用）では全体が O(n log n) に近づく
  - 密な重複入力では従来の O(n²) フォールバックが走る
  - true sweep-line / interval tree の実装は worst case を改善する follow-up として残す
- `Masker.detect` が `normalize(text)` を 1 回だけ計算し、対応する認識器に
  事前正規化済みテキストを渡すよう改良。デフォルト 5 認識器構成で従来は
  4 回呼ばれていた `str.translate` フルスキャンが 1 回に削減される。
  カスタム認識器との後方互換性は `inspect.signature` ベースのオプトイン検出で確保（#24）

### Security

- サーバーモードに API キー認証と CORS 制御を追加（#83、opt-in）:
  - `create_app(api_key="...")` または環境変数 `FUSEJI_API_KEY` で API キーを設定すると、`X-API-Key` ヘッダによる timing-safe な認証が有効化される
  - `/mask` と `/detect` は保護対象、`/healthz` と OpenAPI は未認証で叩ける（ヘルスチェック / ドキュメント生成のため）
  - `create_app(cors_origins=[...])` または環境変数 `FUSEJI_CORS_ORIGINS`（カンマ区切り）で CORS allow_origins を設定すると `starlette.middleware.cors.CORSMiddleware` が組み込まれる
  - デフォルトはどちらも `None`（無認証、CORS 無効、v0.1 互換）。インターネット公開時は両方の設定を強く推奨
- `BodySizeLimitMiddleware` を pure ASGI middleware に書き換え、chunked リクエストでも上限を強制（#87）:
  - Content-Length 宣言の有無に関わらず body stream を逐次読み取り、累積バイト数が `max_bytes` を超えた時点で下流アプリにボディを渡さず 413 を返す
  - chunked transfer-encoding / HTTP/2 / Content-Length 省略経路の DoS を遮断
  - 上限内のリクエストは buffer → replay receive で下流に転送（1MB の bounded buffer なのでメモリ的に許容）
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
