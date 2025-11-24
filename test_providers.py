#!/usr/bin/env python3
"""Test script to verify all providers can be imported and instantiated."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


class MockMissive:
    """Minimal mock missive object for testing."""
    
    def __init__(self):
        self.id = "test_123"
        self.missive_type = "EMAIL"
        self.recipient_email = "test@example.com"
        self.recipient_phone = "+33612345678"
        self.recipient_address = "123 Test Street\n75001 Paris"
        self.subject = "Test Subject"
        self.body = "Test body"
        self.body_text = "Test body"
        self.body_html = None
        self.status = None
        self.provider = None
        self.external_id = None
        self.error_message = None
        self.sent_at = None
        self.delivered_at = None
        self.read_at = None
        self.is_registered = False
        self.requires_signature = False
        
        # Mock recipient
        self.recipient = MockRecipient()
        self.recipient_user = None


class MockRecipient:
    """Minimal mock recipient object for testing."""
    
    def __init__(self):
        self.email = "test@example.com"
        self.mobile = "+33612345678"
        self.name = "Test User"
        self.address_line1 = "123 Test Street"
        self.postal_code = "75001"
        self.city = "Paris"
        self.metadata = {}


def test_provider_import_and_instantiation():
    """Test that all providers can be imported and instantiated."""
    
    providers_to_test = [
        ("SendGridProvider", "python_missive.providers.sendgrid"),
        ("MailgunProvider", "python_missive.providers.mailgun"),
        ("SESProvider", "python_missive.providers.ses"),
        ("DjangoEmailProvider", "python_missive.providers.django_email"),
        ("TwilioProvider", "python_missive.providers.twilio"),
        ("VonageProvider", "python_missive.providers.vonage"),
        ("LaPosteProvider", "python_missive.providers.laposte"),
        ("MailevaProvider", "python_missive.providers.maileva"),
        ("CerteuropeProvider", "python_missive.providers.certeurope"),
        ("SlackProvider", "python_missive.providers.slack"),
        ("TeamsProvider", "python_missive.providers.teams"),
        ("TelegramProvider", "python_missive.providers.telegram"),
        ("SignalProvider", "python_missive.providers.signal"),
        ("MessengerProvider", "python_missive.providers.messenger"),
        ("FCMProvider", "python_missive.providers.fcm"),
        ("InAppNotificationProvider", "python_missive.providers.notification"),
        # Existing providers
        ("BrevoProvider", "python_missive.providers.brevo"),
        ("SMSPartnerProvider", "python_missive.providers.smspartner"),
        ("APNProvider", "python_missive.providers.apn"),
        ("AR24Provider", "python_missive.providers.ar24"),
    ]
    
    results = []
    
    for provider_name, module_path in providers_to_test:
        try:
            # Import the provider
            import importlib

            module = importlib.import_module(module_path)
            provider_class = getattr(module, provider_name)
            
            # Create a mock missive
            missive = MockMissive()
            
            # Set appropriate missive type based on provider
            if provider_name in ["TwilioProvider", "VonageProvider"]:
                missive.missive_type = "SMS"
            elif provider_name in ["LaPosteProvider", "MailevaProvider"]:
                missive.missive_type = "POSTAL"
            elif provider_name in ["CerteuropeProvider"]:
                missive.missive_type = "LRE"
            elif provider_name in ["SlackProvider", "TeamsProvider", "TelegramProvider", 
                                   "SignalProvider", "MessengerProvider"]:
                missive.missive_type = "BRANDED"
            elif provider_name in ["FCMProvider"]:
                missive.missive_type = "PUSH_NOTIFICATION"
            elif provider_name in ["InAppNotificationProvider"]:
                missive.missive_type = "NOTIFICATION"
                missive.recipient_user = MockRecipient()
            
            # Create minimal config
            config: Dict[str, Any] = {}
            if provider_name == "SendGridProvider":
                config = {"SENDGRID_API_KEY": "test_key"}
            elif provider_name == "MailgunProvider":
                config = {"MAILGUN_API_KEY": "test_key", "MAILGUN_DOMAIN": "test.com"}
            elif provider_name == "SESProvider":
                config = {
                    "AWS_ACCESS_KEY_ID": "test_key",
                    "AWS_SECRET_ACCESS_KEY": "test_secret",
                    "AWS_REGION": "eu-west-1",
                    "SES_FROM_EMAIL": "test@example.com"
                }
            elif provider_name == "DjangoEmailProvider":
                config = {
                    "DEFAULT_FROM_EMAIL": "noreply@example.com",
                    "EMAIL_SUPPRESS_SEND": True,
                }
            elif provider_name == "TwilioProvider":
                config = {
                    "TWILIO_ACCOUNT_SID": "test_sid",
                    "TWILIO_AUTH_TOKEN": "test_token",
                    "TWILIO_PHONE_NUMBER": "+33612345678"
                }
            elif provider_name == "VonageProvider":
                config = {
                    "VONAGE_API_KEY": "test_key",
                    "VONAGE_API_SECRET": "test_secret",
                    "VONAGE_FROM_NUMBER": "+33612345678"
                }
            elif provider_name == "LaPosteProvider":
                config = {"LAPOSTE_API_KEY": "test_key"}
            elif provider_name == "MailevaProvider":
                config = {
                    "MAILEVA_CLIENTID": "test_client",
                    "MAILEVA_SECRET": "test_secret",
                    "MAILEVA_USERNAME": "test_user",
                    "MAILEVA_PASSWORD": "test_pass",
                }
            elif provider_name == "CerteuropeProvider":
                config = {
                    "CERTEUROPE_API_KEY": "test_key",
                    "CERTEUROPE_API_SECRET": "test_secret",
                    "CERTEUROPE_API_URL": "https://test.com",
                    "CERTEUROPE_SENDER_EMAIL": "test@example.com"
                }
            elif provider_name == "SlackProvider":
                config = {"SLACK_BOT_TOKEN": "test_token", "SLACK_SIGNING_SECRET": "test_secret"}
            elif provider_name == "TeamsProvider":
                config = {
                    "TEAMS_CLIENT_ID": "test_id",
                    "TEAMS_CLIENT_SECRET": "test_secret",
                    "TEAMS_TENANT_ID": "test_tenant"
                }
            elif provider_name == "TelegramProvider":
                config = {"TELEGRAM_BOT_TOKEN": "test_token"}
            elif provider_name == "SignalProvider":
                config = {"SIGNAL_API_KEY": "test_key"}
            elif provider_name == "MessengerProvider":
                config = {"MESSENGER_PAGE_ACCESS_TOKEN": "test_token", "MESSENGER_VERIFY_TOKEN": "test_token"}
            elif provider_name == "FCMProvider":
                config = {"FCM_SERVER_KEY": "test_key"}
            
            # Instantiate provider
            provider = provider_class(missive=missive, config=config)
            
            # Test basic attributes
            assert hasattr(provider, "name"), f"{provider_name} missing 'name' attribute"
            assert hasattr(provider, "supported_types"), f"{provider_name} missing 'supported_types' attribute"
            assert isinstance(provider.supported_types, list), f"{provider_name}.supported_types should be a list"
            
            # Test validate method
            try:
                is_valid, error = provider.validate()
                assert isinstance(is_valid, bool), f"{provider_name}.validate() should return bool"
                assert isinstance(error, str), f"{provider_name}.validate() should return str"
            except Exception as e:
                results.append((provider_name, False, f"validate() failed: {e}"))
                continue
            
            # Test get_service_status method
            try:
                status = provider.get_service_status()
                assert isinstance(status, dict), f"{provider_name}.get_service_status() should return dict"
            except Exception as e:
                results.append((provider_name, False, f"get_service_status() failed: {e}"))
                continue
            
            # Test supports method
            try:
                supports = provider.supports(missive.missive_type)
                assert isinstance(supports, bool), f"{provider_name}.supports() should return bool"
            except Exception as e:
                results.append((provider_name, False, f"supports() failed: {e}"))
                continue
            
            results.append((provider_name, True, "OK"))
            print(f"✓ {provider_name}: OK")
            
        except ImportError as e:
            results.append((provider_name, False, f"Import error: {e}"))
            print(f"✗ {provider_name}: Import error - {e}")
        except Exception as e:
            results.append((provider_name, False, f"Error: {e}"))
            print(f"✗ {provider_name}: Error - {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    failed = [(name, msg) for name, success, msg in results if not success]
    if failed:
        print("\nFailed providers:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        return False
    
    return True


if __name__ == "__main__":
    success = test_provider_import_and_instantiation()
    exit(0 if success else 1)

