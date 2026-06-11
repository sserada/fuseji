"""fuseji — 日本語特化の PII 検出・マスキングミドルウェア."""

from . import entity_types
from .engine import Masker
from .exceptions import FusejiError, InvalidConfigError, InvalidEntityError
from .strategies import Hash, MaskStrategy, Placeholder, Redact, VaultStrategy
from .types import Entity, MaskResult
from .vault import InMemoryVault, Vault

__version__ = "0.1.0"

__all__ = [
    "Entity",
    "FusejiError",
    "Hash",
    "InMemoryVault",
    "InvalidConfigError",
    "InvalidEntityError",
    "MaskResult",
    "MaskStrategy",
    "Masker",
    "Placeholder",
    "Redact",
    "Vault",
    "VaultStrategy",
    "__version__",
    "entity_types",
]
