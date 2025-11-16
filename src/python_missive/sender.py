"""Missive sending with automatic provider fallback."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Union

from .helpers import get_provider_paths_from_config
from .missive import Missive
from .providers import ProviderImportError, load_provider_class

logger = logging.getLogger(__name__)

# Type alias for providers_config: can be a list of paths or a dict {path: config}
ProvidersConfig = Union[Sequence[str], Dict[str, Dict[str, Any]]]


class MissiveSender:
    """Sends missives with automatic provider fallback."""

    def __init__(
        self,
        providers_config: Optional[ProvidersConfig] = None,
        default_config: Optional[Dict[str, Any]] = None,
        sandbox: bool = False,
    ):
        """Initialize sender with optional provider configuration.

        Args:
            providers_config: Either:
                - List of provider import paths (e.g., ["python_missive.providers.brevo.BrevoProvider"])
                - Dict mapping provider paths to their configs (e.g., {"path": {"API_KEY": "value"}})
            default_config: Default configuration dict merged with provider-specific configs
            sandbox: If True, forces sandbox mode for all providers (no real sends)
        """
        self.providers_config = providers_config
        self.default_config = default_config or {}
        self.sandbox = sandbox

        # Extract provider paths if config is a dict
        if isinstance(providers_config, dict):
            self._provider_configs = providers_config
            self._provider_paths = list(providers_config.keys())
        else:
            self._provider_configs = {}
            self._provider_paths = list(providers_config) if providers_config else []

    def get_provider_paths(self, missive: Missive) -> List[str]:
        """Return ordered list of provider paths to try (by priority).

        Providers are determined from the configuration passed to the sender.
        If no providers_config is provided, returns empty list.
        """
        if missive.provider:
            logger.info(f"Missive: Explicit provider '{missive.provider}'")
            return [missive.provider]

        if not self.providers_config:
            raise ValueError(
                f"No providers_config provided and no explicit provider set for {missive.missive_type}"
            )

        # Use provider paths (extracted from dict if needed)
        providers_by_type = get_provider_paths_from_config(self._provider_paths)
        provider_paths = providers_by_type.get(missive.missive_type.upper())

        if not provider_paths:
            raise ValueError(
                f"No provider configured for {missive.missive_type}. "
                f"Available types: {list(providers_by_type.keys())}"
            )

        logger.info(
            f"Missive: Configured providers for {missive.missive_type}: {provider_paths}"
        )
        return provider_paths

    def get_provider_config(self, provider_path: str) -> Dict[str, Any]:
        """Get configuration for a specific provider, merged with default config.

        Args:
            provider_path: Full import path of the provider

        Returns:
            Merged configuration dict (provider-specific config takes precedence)
        """
        provider_config = self._provider_configs.get(provider_path, {})
        # Merge: default_config first, then provider-specific config (provider wins)
        return {**self.default_config, **provider_config}

    def send(
        self,
        missive: Missive,
        enable_fallback: bool = True,
        **provider_kwargs: Any,
    ) -> bool:
        """Send missive via appropriate provider with automatic fallback.

        If sandbox mode is enabled, forces sandbox=True in provider_options.

        Args:
            missive: Missive object to send
            enable_fallback: If True, try next provider on failure
            **provider_kwargs: Additional kwargs to pass to provider constructor

        Returns:
            True if sent successfully, False otherwise

        Raises:
            RuntimeError: If all providers fail and enable_fallback is True
            ValueError: If no providers are configured
        """
        # Force sandbox mode if enabled globally
        if self.sandbox:
            if not missive.provider_options:
                missive.provider_options = {}
            # Force sandbox=True (unless explicitly disabled)
            if "sandbox" not in missive.provider_options:
                missive.provider_options["sandbox"] = True
        if not missive.can_send():
            logger.warning("Missive: Cannot be sent (can_send()=False)")
            return False

        provider_paths = self.get_provider_paths(missive)

        if not provider_paths:
            raise ValueError(f"No provider configured for {missive.missive_type}")

        logger.info(
            f"Missive: Attempting to send with {len(provider_paths)} available provider(s)"
        )

        last_error = None
        attempts = []

        for index, provider_path in enumerate(provider_paths, 1):
            try:
                provider_class = load_provider_class(provider_path)
                provider_name = provider_class.__name__

                logger.info(
                    f"Missive: Attempt {index}/{len(provider_paths)} with {provider_name}"
                )

                # Get provider-specific config (merged with default)
                provider_config = self.get_provider_config(provider_path)

                # Instantiate provider with missive and config
                provider = provider_class(
                    missive=missive,
                    config=provider_config,
                    **provider_kwargs,
                )
                # BaseProvider has send() method, but mypy doesn't know it
                if hasattr(provider, "send"):
                    success = provider.send()  # type: ignore[attr-defined]
                else:
                    raise RuntimeError(f"Provider {provider_path} does not have send() method")

                if success:
                    logger.info(
                        f"Missive: ✅ Sent successfully via {provider_name} "
                        f"(attempt {index}/{len(provider_paths)})"
                    )
                    attempts.append(
                        {
                            "provider": provider_name,
                            "status": "success",
                            "attempt": index,
                        }
                    )

                    # Update the provider used on the missive
                    missive.provider = provider_path
                    return True
                else:
                    logger.warning(f"Missive: ❌ Failed with {provider_name}")
                    attempts.append(
                        {
                            "provider": provider_name,
                            "status": "failed",
                            "attempt": index,
                        }
                    )

                    if not enable_fallback:
                        raise RuntimeError(f"Send failed with {provider_name}")

            except ProviderImportError as e:
                error_msg = f"Provider '{provider_path}' not found: {e}"
                logger.error(f"Missive: {error_msg}")
                last_error = error_msg
                attempts.append(
                    {
                        "provider": provider_path,
                        "status": "import_error",
                        "error": str(e),
                    }
                )

                if not enable_fallback:
                    raise ValueError(error_msg)

            except Exception as e:
                error_msg = f"Error sending with {provider_path}: {e}"
                logger.error(f"Missive: {error_msg}")
                last_error = error_msg
                attempts.append(
                    {"provider": provider_path, "status": "exception", "error": str(e)}
                )

                if not enable_fallback:
                    raise

        # If we get here, all providers failed
        error_summary = "All providers failed. "
        error_summary += f"Attempts: {attempts}. "
        if last_error:
            error_summary += f"Last error: {last_error}"

        logger.error(error_summary)
        raise RuntimeError(error_summary)
