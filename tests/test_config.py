"""Test configuration for provider discovery.

This configuration mirrors the structure from django-missive/tests/settings.py
but uses pymissive.providers.* paths instead of missive.providers.*

To add a new provider:
1. Add its import path as a key in MISSIVE_CONFIG_PROVIDERS below
2. Provide default test configuration (API keys, etc.) as the value
3. The provider will be automatically categorized by its supported_types
4. Use instantiate_provider() in tests with the short name (e.g., "brevo", "apn")

Environment variables from .env file will override default values if present.
"""

import os
from typing import Any, Dict, Optional, Type

try:
    from geoaddress import BaseAddressBackend
except ImportError:
    from pymissive.address_backends import BaseAddressBackend


def _get_env_or_default(key: str, default: str) -> str:
    """Get environment variable or return default value."""
    return os.getenv(key, default)


MISSIVE_CONFIG_PROVIDERS = {
    # Email providers
    "pymissive.providers.brevo.BrevoProvider": {
        "BREVO_API_KEY": _get_env_or_default("BREVO_API_KEY", "test_token"),
        "BREVO_DEFAULT_FROM_EMAIL": _get_env_or_default(
            "BREVO_DEFAULT_FROM_EMAIL", "noreply@example.com"
        ),
        "BREVO_SMS_SENDER": _get_env_or_default("BREVO_SMS_SENDER", ""),
    },
    "pymissive.providers.sendgrid.SendGridProvider": {
        "SENDGRID_API_KEY": _get_env_or_default("SENDGRID_API_KEY", "test_key"),
    },
    "pymissive.providers.mailgun.MailgunProvider": {
        "MAILGUN_API_KEY": _get_env_or_default("MAILGUN_API_KEY", "test_key"),
        "MAILGUN_DOMAIN": _get_env_or_default("MAILGUN_DOMAIN", "test.example.com"),
    },
    "pymissive.providers.smtp.SMTPProvider": {
        "SMTP_HOST": _get_env_or_default("SMTP_HOST", "localhost"),
        "SMTP_PORT": int(_get_env_or_default("SMTP_PORT", "1025")),
        "SMTP_USERNAME": _get_env_or_default("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": _get_env_or_default("SMTP_PASSWORD", ""),
        "SMTP_USE_TLS": _get_env_or_default("SMTP_USE_TLS", "false"),
        "SMTP_USE_SSL": _get_env_or_default("SMTP_USE_SSL", "false"),
        "SMTP_TIMEOUT_SECONDS": float(
            _get_env_or_default("SMTP_TIMEOUT_SECONDS", "5.0")
        ),
        "DEFAULT_FROM_EMAIL": _get_env_or_default(
            "SMTP_DEFAULT_FROM_EMAIL", "noreply@example.com"
        ),
    },
    "pymissive.providers.ses.SESProvider": {
        "AWS_ACCESS_KEY_ID": _get_env_or_default("AWS_ACCESS_KEY_ID", "test_key"),
        "AWS_SECRET_ACCESS_KEY": _get_env_or_default(
            "AWS_SECRET_ACCESS_KEY", "test_secret"
        ),
        "AWS_REGION": _get_env_or_default("AWS_REGION", "us-east-1"),
        "SES_FROM_EMAIL": _get_env_or_default("SES_FROM_EMAIL", "noreply@example.com"),
    },
    # SMS/Voice providers (multi-types)
    "pymissive.providers.smspartner.SMSPartnerProvider": {
        "SMSPARTNER_API_KEY": _get_env_or_default("SMSPARTNER_API_KEY", "test_key"),
        "SMSPARTNER_SENDER": _get_env_or_default("SMSPARTNER_SENDER", "TestSender"),
        "SMSPARTNER_WEBHOOK_IPS": _get_env_or_default("SMSPARTNER_WEBHOOK_IPS", ""),
        "SMSPARTNER_WEBHOOK_URL": _get_env_or_default("SMSPARTNER_WEBHOOK_URL", ""),
        "DEFAULT_FROM_EMAIL": _get_env_or_default("DEFAULT_FROM_EMAIL", ""),
        "DEFAULT_FROM_NAME": _get_env_or_default("DEFAULT_FROM_NAME", ""),
    },
    "pymissive.providers.twilio.TwilioProvider": {
        "TWILIO_ACCOUNT_SID": _get_env_or_default("TWILIO_ACCOUNT_SID", "test_sid"),
        "TWILIO_AUTH_TOKEN": _get_env_or_default("TWILIO_AUTH_TOKEN", "test_token"),
        "TWILIO_PHONE_NUMBER": _get_env_or_default(
            "TWILIO_PHONE_NUMBER", "+1234567890"
        ),
    },
    "pymissive.providers.vonage.VonageProvider": {
        "VONAGE_API_KEY": _get_env_or_default("VONAGE_API_KEY", "test_key"),
        "VONAGE_API_SECRET": _get_env_or_default("VONAGE_API_SECRET", "test_secret"),
        "VONAGE_FROM_NUMBER": _get_env_or_default("VONAGE_FROM_NUMBER", "+1234567890"),
    },
    # Postal/LRE providers
    "pymissive.providers.ar24.AR24Provider": {
        "AR24_API_TOKEN": _get_env_or_default("AR24_API_TOKEN", ""),
        "AR24_API_URL": _get_env_or_default("AR24_API_URL", "https://api.ar24.fr"),
        "AR24_SENDER_ID": _get_env_or_default("AR24_SENDER_ID", ""),
    },
    "pymissive.providers.laposte.LaPosteProvider": {
        "LAPOSTE_API_KEY": _get_env_or_default("LAPOSTE_API_KEY", "test_key"),
    },
    "pymissive.providers.maileva.MailevaProvider": {
        "MAILEVA_CLIENTID": _get_env_or_default("MAILEVA_CLIENTID", "test_client"),
        "MAILEVA_SECRET": _get_env_or_default("MAILEVA_SECRET", "test_secret"),
        "MAILEVA_USERNAME": _get_env_or_default("MAILEVA_USERNAME", "test_user"),
        "MAILEVA_PASSWORD": _get_env_or_default("MAILEVA_PASSWORD", "test_pass"),
    },
    "pymissive.providers.certeurope.CerteuropeProvider": {
        "CERTEUROPE_API_KEY": _get_env_or_default("CERTEUROPE_API_KEY", "test_key"),
        "CERTEUROPE_API_SECRET": _get_env_or_default(
            "CERTEUROPE_API_SECRET", "test_secret"
        ),
        "CERTEUROPE_API_URL": _get_env_or_default(
            "CERTEUROPE_API_URL", "https://api.certeurope.fr"
        ),
        "CERTEUROPE_SENDER_EMAIL": _get_env_or_default(
            "CERTEUROPE_SENDER_EMAIL", "noreply@example.com"
        ),
    },
    # Push notification providers
    "pymissive.providers.apn.APNProvider": {
        "APN_CERTIFICATE_PATH": _get_env_or_default("APN_CERTIFICATE_PATH", ""),
        "APN_KEY_ID": _get_env_or_default("APN_KEY_ID", ""),
        "APN_TEAM_ID": _get_env_or_default("APN_TEAM_ID", ""),
    },
    "pymissive.providers.fcm.FCMProvider": {
        "FCM_SERVER_KEY": _get_env_or_default("FCM_SERVER_KEY", "test_key"),
    },
    # Branded messaging providers
    "pymissive.providers.telegram.TelegramProvider": {
        "TELEGRAM_BOT_TOKEN": _get_env_or_default("TELEGRAM_BOT_TOKEN", "test_token"),
    },
    "pymissive.providers.slack.SlackProvider": {
        "SLACK_BOT_TOKEN": _get_env_or_default("SLACK_BOT_TOKEN", "test_token"),
        "SLACK_SIGNING_SECRET": _get_env_or_default(
            "SLACK_SIGNING_SECRET", "test_secret"
        ),
    },
    "pymissive.providers.teams.TeamsProvider": {
        "TEAMS_CLIENT_ID": _get_env_or_default("TEAMS_CLIENT_ID", "test_client_id"),
        "TEAMS_CLIENT_SECRET": _get_env_or_default(
            "TEAMS_CLIENT_SECRET", "test_secret"
        ),
        "TEAMS_TENANT_ID": _get_env_or_default("TEAMS_TENANT_ID", "test_tenant_id"),
    },
    "pymissive.providers.signal.SignalProvider": {
        "SIGNAL_API_KEY": _get_env_or_default("SIGNAL_API_KEY", "test_key"),
    },
    "pymissive.providers.messenger.MessengerProvider": {
        "MESSENGER_PAGE_ACCESS_TOKEN": _get_env_or_default(
            "MESSENGER_PAGE_ACCESS_TOKEN", "test_token"
        ),
        "MESSENGER_VERIFY_TOKEN": _get_env_or_default(
            "MESSENGER_VERIFY_TOKEN", "test_verify"
        ),
    },
    # In-app notification provider (no config needed)
    "pymissive.providers.notification.InAppNotificationProvider": {},
}

# =============================================================================
# Address verification backends configuration
# =============================================================================
# Ordered list of address backends to try. The first working backend will be used.
# Backends are tested in order until one is successfully configured and working.

MISSIVE_CONFIG_ADDRESS_BACKENDS = [
    # Free backends (no API key required) - try these first
    {
        "class": "pymissive.address_backends.nominatim.NominatimAddressBackend",
        "config": {
            "NOMINATIM_USER_AGENT": _get_env_or_default(
                "NOMINATIM_USER_AGENT", "python-missive-test/1.0"
            ),
            "NOMINATIM_BASE_URL": _get_env_or_default(
                "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
            ),
        },
    },
    {
        "class": "pymissive.address_backends.photon.PhotonAddressBackend",
        "config": {
            "PHOTON_BASE_URL": _get_env_or_default(
                "PHOTON_BASE_URL", "https://photon.komoot.io"
            ),
        },
    },
    # Free tier backends (API key required, but free tier available) - try these next
    {
        "class": "pymissive.address_backends.locationiq.LocationIQAddressBackend",
        "config": {
            "LOCATIONIQ_API_KEY": _get_env_or_default("LOCATIONIQ_API_KEY", ""),
            "LOCATIONIQ_BASE_URL": _get_env_or_default(
                "LOCATIONIQ_BASE_URL", "https://api.locationiq.com/v1"
            ),
        },
    },
    {
        "class": "pymissive.address_backends.opencage.OpenCageAddressBackend",
        "config": {
            "OPENCAGE_API_KEY": _get_env_or_default("OPENCAGE_API_KEY", ""),
            "OPENCAGE_BASE_URL": _get_env_or_default(
                "OPENCAGE_BASE_URL", "https://api.opencagedata.com/geocode/v1"
            ),
        },
    },
    {
        "class": "pymissive.address_backends.geocode_earth.GeocodeEarthAddressBackend",
        "config": {
            "GEOCODE_EARTH_API_KEY": _get_env_or_default("GEOCODE_EARTH_API_KEY", ""),
            "GEOCODE_EARTH_BASE_URL": _get_env_or_default(
                "GEOCODE_EARTH_BASE_URL", "https://api.geocode.earth/v1"
            ),
        },
    },
    {
        "class": "pymissive.address_backends.geoapify.GeoapifyAddressBackend",
        "config": {
            "GEOAPIFY_API_KEY": _get_env_or_default("GEOAPIFY_API_KEY", ""),
            "GEOAPIFY_BASE_URL": _get_env_or_default(
                "GEOAPIFY_BASE_URL", "https://api.geoapify.com/v1"
            ),
        },
    },
    {
        "class": "pymissive.address_backends.maps_co.MapsCoAddressBackend",
        "config": {
            "MAPS_CO_API_KEY": _get_env_or_default("MAPS_CO_API_KEY", ""),
            "MAPS_CO_BASE_URL": _get_env_or_default(
                "MAPS_CO_BASE_URL", "https://geocode.maps.co"
            ),
        },
    },
    # Paid backends (API key required) - try these if free ones fail
    {
        "class": "pymissive.address_backends.google_maps.GoogleMapsAddressBackend",
        "config": {
            "GOOGLE_MAPS_API_KEY": _get_env_or_default("GOOGLE_MAPS_API_KEY", ""),
        },
    },
    {
        "class": "pymissive.address_backends.mapbox.MapboxAddressBackend",
        "config": {
            "MAPBOX_ACCESS_TOKEN": _get_env_or_default("MAPBOX_ACCESS_TOKEN", ""),
        },
    },
    {
        "class": "pymissive.address_backends.here.HereAddressBackend",
        "config": {
            "HERE_APP_ID": _get_env_or_default("HERE_APP_ID", ""),
            "HERE_APP_CODE": _get_env_or_default("HERE_APP_CODE", ""),
        },
    },
]

# Note: Providers with multiple supported_types are automatically categorized
# according to their supported_types. No need to repeat them!
# The test suite uses helpers.get_providers_from_config() to load and group providers.


def _load_address_backend_class(backend_path: str) -> Type[BaseAddressBackend]:
    """Load an address backend class from its import path.

    This is a wrapper around the function in helpers.py for backward compatibility.
    """
    from pymissive.helpers import \
        _load_address_backend_class as load_class

    return load_class(backend_path)


def get_working_address_backend(
    test_address: Optional[Dict[str, Any]] = None,
) -> Optional[BaseAddressBackend]:
    """Get the first working address backend from configuration.

    Tests backends in order until one is successfully configured and working.
    If a backend is not configured or fails, tries the next one.

    Args:
        test_address: Optional test address to validate backend functionality.
            If None, uses a default test address.

    Returns:
        First working backend instance, or None if all backends fail.

    Example:
        >>> backend = get_working_address_backend()
        >>> if backend:
        ...     result = backend.validate_address("123 Main St", city="Paris", country="FR")
        ...     print(f"Address valid: {result['is_valid']}")
    """
    from pymissive.helpers import get_address_backends_from_config

    if test_address is None:
        test_address = {
            "address_line1": "123 Test Street",
            "city": "Paris",
            "postal_code": "75001",
            "country": "FR",
        }

    # Get configured backends
    backends = get_address_backends_from_config(MISSIVE_CONFIG_ADDRESS_BACKENDS)

    # Try to validate with each backend until one works
    for backend in backends:
        try:
            result = backend.validate_address(**test_address)
            errors = result.get("errors", [])
            critical_errors = [
                e
                for e in errors
                if "not configured" in e.lower()
                or "not installed" in e.lower()
                or ("error" in e.lower() and "no address found" not in e.lower())
            ]
            if not critical_errors:
                return backend
        except Exception:
            continue

    return None
