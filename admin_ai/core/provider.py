"""Provider-independent AI interface. Concrete providers live in admin_ai/providers."""
from abc import ABC, abstractmethod
from typing import Sequence

from admin_ai.core.types import Message, ProviderError, ProviderResponse, ToolDefinition

__all__ = ["AIProvider", "ProviderError"]


class AIProvider(ABC):
    """Contract: translate neutral messages/tools to a vendor API and return a *validated*, neutral response.

    Implementations must raise ProviderError(code) for every failure (timeout, transport, bad status,
    malformed response) and must never include secrets or raw vendor error text in the code.
    """

    @abstractmethod
    def generate(self, messages: Sequence[Message], tools: Sequence[ToolDefinition]) -> ProviderResponse:
        ...
