# fuseji-bench

`pytest-benchmark` ベースのパフォーマンスベンチ。

## 実行

```bash
uv sync --all-extras  # pytest-benchmark を含む
uv run pytest tests/bench/ --benchmark-only -v
```

通常の `uv run pytest` ではベンチは自動収集される（`--benchmark-disable` で時間計測なし）。回帰検知のために CI でも回す。

## 構成

- `bench_masker.py`: full pipeline（detect → mask）のレイテンシ
- `bench_recognizers.py`: 各認識器単独のレイテンシ
- `bench_replace_spans.py`: `_replace_spans` のスケール曲線
- `bench_vault.py`: `InMemoryVault.restore` のスケール曲線
- `bench_resolve_overlaps.py`: `_resolve_overlaps` の entity 数スケール曲線（#98）
- `bench_mask_json.py`: `Masker.mask_json` の leaf 数 / ネスト深度スケール（#98）
- `bench_strategies.py`: Placeholder / Redact / Hash / VaultStrategy の横並び比較（#98）

## レイテンシ目標（design_docs §2 より）

- 正規表現/checksum 層: < 1 ms per KB
- NER 層: < 100 ms per ~100 tokens（GiNZA、CPU）

回帰検知 assertion 付きのテストは `tests/test_latency_regression.py` に実装済み
（`test_masker_1KB_は_5ms_未満` / `test_masker_4KB_は_20ms_未満` / `test_vault_restore_は_m1000_でも_10ms_未満`）。
通常 CI ではノイズによる偽陽性を避けるためデフォルトスキップで、`CI_PERF=1` を
設定したジョブまたはローカル検証でのみ実行される（詳細は下の「CI 信頼性」節を参照）。

## 結果比較

```bash
# main で計測
git checkout main && uv run pytest tests/bench/ --benchmark-only --benchmark-save=main

# 改善 PR で計測 → main と比較
uv run pytest tests/bench/ --benchmark-only --benchmark-compare=main
```

## 環境マーカー (#92)

ベンチマーク結果は実行環境（CPU アーキテクチャ・OS）に強く依存する。
開発者ローカル (例: darwin-arm64) と CI (linux-x86_64) で baseline を
取り違えると 2-3x ぶれて誤判定する。

`tests/bench/conftest.py` が machine_info に `fuseji_env_key`
（例: `darwin-arm64`, `linux-x86_64`）を埋め込む。**baseline ファイル名に
これを含める運用を推奨**:

```bash
# 環境ごとに baseline を分離
ENV_KEY=$(python -c 'import platform; print(f"{platform.system().lower()}-{platform.machine().lower()}")')
uv run pytest tests/bench/ --benchmark-only --benchmark-save="main-${ENV_KEY}"

# 改善 PR を同じ環境で計測 → 比較
uv run pytest tests/bench/ --benchmark-only --benchmark-compare="main-${ENV_KEY}"
```

## CI 信頼性 — `test_latency_regression.py` (#92)

`tests/test_latency_regression.py` の閾値テスト（1KB 5ms 未満 等）は
**デフォルトでスキップ**される。通常 CI の test ジョブで CI ランナー
のノイズ（thermal throttling、neighboring tenant CPU contention）で
偽陽性が起きやすいため。

専用 perf-CI ジョブまたはローカル検証で `CI_PERF=1` を設定して実行する:

```bash
CI_PERF=1 uv run pytest tests/test_latency_regression.py
```

正常性確認は通常の単体テストで担保し、本テストは O(n²) 回帰など
**桁オーダーの劣化**を狙って実行する位置づけ。
