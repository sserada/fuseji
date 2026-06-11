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

## レイテンシ目標（design_docs §2 より）

- 正規表現/checksum 層: < 1 ms per KB
- NER 層: < 100 ms per ~100 tokens（GiNZA、CPU）

`bench_masker.py` の `test_masker_1kb_regex_only` などで上記目標を assertion 付きで失敗させる回帰検知テスト化を予定（v0.2 中盤で）。

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
