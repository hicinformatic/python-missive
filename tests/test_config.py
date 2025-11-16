"""Test configuration for provider discovery.

This configuration mirrors the structure from django-missive/tests/settings.py
but uses python_missive.providers.* paths instead of missive.providers.*

To add a new provider:
1. Add its import path as a key in MISSIVE_CONFIG_PROVIDERS below
2. Provide default test configuration (API keys, etc.) as the value
3. The provider will be automatically categorized by its supported_types
4. Use instantiate_provider() in tests with the short name (e.g., "brevo", "apn")

Environment variables from .env file will override default values if present.
"""

import os


def _get_env_or_default(key: str, default: str) -> str:
    """Get environment variable or return default value."""
    return os.getenv(key, default)


MISSIVE_CONFIG_PROVIDERS = {
    # Email providers
    "python_missive.providers.brevo.BrevoProvider": {
        "BREVO_API_KEY": _get_env_or_default("BREVO_API_KEY", "test_token"),
        "BREVO_DEFAULT_FROM_EMAIL": _get_env_or_default(
            "BREVO_DEFAULT_FROM_EMAIL", "noreply@example.com"
        ),
        "BREVO_SMS_SENDER": _get_env_or_default("BREVO_SMS_SENDER", ""),
    },
    # SMS/Voice providers (multi-types)
    "python_missive.providers.smspartner.SMSPartnerProvider": {
        "SMSPARTNER_API_KEY": _get_env_or_default("SMSPARTNER_API_KEY", "test_key"),
        "SMSPARTNER_SENDER": _get_env_or_default("SMSPARTNER_SENDER", "TestSender"),
        "SMSPARTNER_WEBHOOK_IPS": _get_env_or_default("SMSPARTNER_WEBHOOK_IPS", ""),
        "SMSPARTNER_WEBHOOK_URL": _get_env_or_default("SMSPARTNER_WEBHOOK_URL", ""),
        "DEFAULT_FROM_EMAIL": _get_env_or_default("DEFAULT_FROM_EMAIL", ""),
        "DEFAULT_FROM_NAME": _get_env_or_default("DEFAULT_FROM_NAME", ""),
    },
    # Postal/LRE providers
    "python_missive.providers.ar24.AR24Provider": {
        "AR24_API_TOKEN": _get_env_or_default("AR24_API_TOKEN", ""),
        "AR24_API_URL": _get_env_or_default("AR24_API_URL", "https://api.ar24.fr"),
        "AR24_SENDER_ID": _get_env_or_default("AR24_SENDER_ID", ""),
    },
    # Push notification providers
    "python_missive.providers.apn.APNProvider": {
        "APN_CERTIFICATE_PATH": _get_env_or_default("APN_CERTIFICATE_PATH", ""),
        "APN_KEY_ID": _get_env_or_default("APN_KEY_ID", ""),
        "APN_TEAM_ID": _get_env_or_default("APN_TEAM_ID", ""),
    },
}

# Note: Providers with multiple supported_types are automatically categorized
# according to their supported_types. No need to repeat them!
# The test suite uses helpers.get_providers_from_config() to load and group providers.
