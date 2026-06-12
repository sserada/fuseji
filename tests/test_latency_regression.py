"""レイテンシ目標の回帰検知テスト。

設計目標（design_docs §2）:
- 正規表現/checksum 層: < 1 ms per KB
- NER 層: < 100 ms per ~100 tokens（このテストでは検証しない）

ここでは O(n²) バグなどの**性能回帰**を即時検知する目的で、
GitHub Actions ubuntu-latest（Apple M1 比でおおむね 2-3x 遅い）
を念頭に **3x 余裕** を持たせた上限値で assertion する。

CI 環境のノイズで誤検知が起きやすいため、デフォルトではスキップされ、
環境変数 ``CI_PERF=1`` を設定したジョブでのみ実行される (#92)。
ローカルや専用 perf-CI ジョブで設定すること:

    CI_PERF=1 uv run pytest tests/test_latency_regression.py

詳細な計測・スケール曲線・他ツール比較は tests/bench/ を参照。
"""

from __future__ import annotations

import gc
import os
import time

import pytest

from fuseji import InMemoryVault, Masker

# CI_PERF=1 を設定したジョブでのみ実行する。デフォルトはスキップ。
# 通常 CI の test ジョブで thermal throttling 等で偽陽性が起きやすいため。
_RUN_PERF_TESTS = os.getenv("CI_PERF") == "1"
_SKIP_REASON = "perf テストは CI_PERF=1 のジョブでのみ実行（CI ノイズで誤検知防止）"
pytestmark = pytest.mark.skipif(not _RUN_PERF_TESTS, reason=_SKIP_REASON)


def _measure(fn, iterations: int = 20, warmup: int = 3) -> float:
    """fn を warmup 回呼んだ後 iterations 回計測し、平均秒を返す."""
    for _ in range(warmup):
        fn()
    gc.collect()
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    return (time.perf_counter() - start) / iterations


def _build_text(kb: int) -> str:
    chunk = (
        "問い合わせ番号 〒123-4567、"
        "連絡先 090-1234-5678 / taro@example.co.jp、"
        "クレジットカード 4242-4242-4242-4242 です。\n"
    )
    target_bytes = kb * 1024
    chunks_needed = max(1, target_bytes // len(chunk.encode("utf-8")))
    return chunk * chunks_needed


class TestMaskerLatency:
    def test_masker_1KB_は_5ms_未満(self) -> None:
        """1KB 入力で 5ms 未満。target は 1ms、3-5x の CI 余裕。"""
        masker = Masker()
        text = _build_text(1)
        avg = _measure(lambda: masker.mask(text))
        assert avg < 0.005, f"1KB が遅い: {avg * 1000:.2f}ms (target < 5ms)"

    def test_masker_4KB_は_20ms_未満(self) -> None:
        """4KB 入力で 20ms 未満（4ms target * 5x 余裕）."""
        masker = Masker()
        text = _build_text(4)
        avg = _measure(lambda: masker.mask(text), iterations=10)
        assert avg < 0.020, f"4KB が遅い: {avg * 1000:.2f}ms (target < 20ms)"


class TestJpAddressPathologicalLatency:
    """JpAddressRecognizer の worst-case 入力に対する線形性回帰防止 (#141).

    都道府県 anchor + マッチ失敗を誘発する長大漢字列。bounded quantifier 化
    前は 1 マッチ試行ごとに greedy 消費 → 1 文字ずつ縮めて再判定する経路があり、
    O(n²) 級になる可能性があった。
    """

    def _pathological(self, kb: int) -> str:
        return "東京都" + "亜" * (kb * 1024)

    def test_pathological_4KB_は_50ms_未満(self) -> None:
        from fuseji.recognizers.jp_address import JpAddressRecognizer

        recognizer = JpAddressRecognizer()
        text = self._pathological(4)
        avg = _measure(lambda: list(recognizer.analyze(text)), iterations=10)
        assert avg < 0.050, f"4KB pathological が遅い: {avg * 1000:.2f}ms (target < 50ms)"

    def test_pathological_16KB_は_200ms_未満(self) -> None:
        from fuseji.recognizers.jp_address import JpAddressRecognizer

        recognizer = JpAddressRecognizer()
        text = self._pathological(16)
        avg = _measure(lambda: list(recognizer.analyze(text)), iterations=5)
        assert avg < 0.200, f"16KB pathological が遅い: {avg * 1000:.2f}ms (target < 200ms)"


class TestVaultRestoreLatency:
    def test_vault_restore_は_m1000_でも_10ms_未満(self) -> None:
        """1000 placeholders 登録された Vault に対し restore が 10ms 未満。

        #22 の regex 化前は O(m·n) だったので、m=1000 で大幅遅延の
        regression を検知できる。
        """
        vault = InMemoryVault()
        for i in range(1000):
            vault.assign("PERSON", f"name_{i}")
        text = "".join(f"<PERSON_{i % 100 + 1}> さん。" for i in range(100))
        avg = _measure(lambda: vault.restore(text), iterations=10)
        assert avg < 0.010, f"restore が遅い: {avg * 1000:.2f}ms (target < 10ms)"
