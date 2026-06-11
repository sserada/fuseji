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
