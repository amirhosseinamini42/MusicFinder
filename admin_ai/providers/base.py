"""Compatibility re-export. The provider contract is owned by Agent Core (admin_ai.core.provider)."""
from admin_ai.core.provider import AIProvider, ProviderError

__all__ = ["AIProvider", "ProviderError"]
