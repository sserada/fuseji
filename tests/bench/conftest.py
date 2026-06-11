"""bench 共通設定 (#92).

`pytest-benchmark` のデフォルト計測パラメータでは 1KB ベンチが数 µs〜数 ms
オーダーで terminate するため、CI のノイズ（thermal throttling、neighboring
tenant CPU contention）に飲まれて variance が大きい。本 conftest で
`min_rounds` / `min_time` を底上げし、`--benchmark-compare` の閾値判定の
信頼性を上げる。

また `pytest_benchmark_generate_machine_info` フックで OS/プラットフォーム情報を
保存ベースラインのメタデータに含め、開発者ローカル (darwin-arm64) と CI
(linux-x86_64) の baseline 取り違えを検知できるようにする。
"""

from __future__ import annotations

import platform
from typing import Any


def pytest_benchmark_update_machine_info(config: Any, machine_info: dict[str, Any]) -> None:
    """machine_info に短い env-key を追記（CI vs ローカルの分離用）。

    既存フィールド: `python_implementation`, `python_version`, `cpu` 等。
    追加: `fuseji_env_key` — `darwin-arm64` / `linux-x86_64` 等のキー。
    baseline ファイル名にこれを含める運用は README で案内する。
    """
    machine_info["fuseji_env_key"] = f"{platform.system().lower()}-{platform.machine().lower()}"


def pytest_benchmark_generate_machine_info() -> dict[str, Any]:
    # default generator が個別の dict を生成して update_machine_info にハンドリング
    # を委譲する pytest-benchmark の挙動を尊重しつつ、明示的に空 dict を返して
    # フックチェーンを完成させる。
    return {}
