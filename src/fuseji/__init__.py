"""fuseji — 日本語特化の PII 検出・マスキングミドルウェア."""

from .engine import Masker
from .strategies import Hash, MaskStrategy, Placeholder, Redact
from .types import Entity, MaskResult
from .vault import InMemoryVault, Vault

__version__ = "0.1.0"

__all__ = [
    "Entity",
    "Hash",
    "InMemoryVault",
    "MaskResult",
    "MaskStrategy",
    "Masker",
    "Placeholder",
    "Redact",
    "Vault",
    "__version__",
]
