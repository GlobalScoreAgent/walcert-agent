from __future__ import annotations


class ProviderError(Exception):
    """External data provider failure."""

    def __init__(self, provider: str, message: str, status_code: int | None = None):
        self.provider = provider
        self.message = message
        self.status_code = status_code
        super().__init__(f"{provider}: {message}")


class QuotaExceeded(Exception):
    """Local free-tier budget exhausted for a provider."""

    def __init__(self, provider: str, retry_after: str):
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"quota exceeded for {provider}")


class MissingCredentials(Exception):
    """Required API key is not configured."""

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"missing credentials for {provider}")
