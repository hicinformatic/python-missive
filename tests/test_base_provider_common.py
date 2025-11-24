"""Tests for the framework-agnostic BaseProviderCommon."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from python_missive.providers.base import BaseProviderCommon
from python_missive.status import MissiveStatus


class DummyMissive:
    """Lightweight missive object used to exercise state helpers."""

    def __init__(self) -> None:
        self.status: MissiveStatus | None = None
        self.provider: str | None = None
        self.external_id: str | None = None
        self.error_message: str | None = None
        self.sent_at: datetime | None = None
        self.delivered_at: datetime | None = None
        self.read_at: datetime | None = None
        self.missive_type: str = "EMAIL"
        self.is_registered: bool = False
        self.requires_signature: bool = False
        self.save_calls: int = 0

    def save(self) -> None:
        self.save_calls += 1


class DummyProvider(BaseProviderCommon):
    """Provider subclass used for unit tests."""

    name = "Dummy"
    supported_types = ["EMAIL", "SMS"]
    services = ["tracking", "proofs"]
    config_keys = ["DUMMY_API_KEY", "TIMEOUT"]


def frozen_clock():
    """Return a deterministic timestamp for assertions."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_config_filtering() -> None:
    provider = DummyProvider(
        missive=None,
        config={
            "DUMMY_API_KEY": "secret",
            "TIMEOUT": 5,
            "IGNORED": True,
        },
    )

    assert provider.config == {"DUMMY_API_KEY": "secret", "TIMEOUT": 5}
    assert provider._raw_config["IGNORED"] is True


def test_support_checks() -> None:
    provider = DummyProvider()

    assert provider.supports("EMAIL") is True
    assert provider.supports("PUSH_NOTIFICATION") is False
    assert provider.has_service("tracking") is True
    assert provider.has_service("invalid") is False


def test_update_status_sets_fields_and_timestamps() -> None:
    missive = DummyMissive()
    provider = DummyProvider(missive=missive, clock=frozen_clock)

    provider._update_status(
        MissiveStatus.SENT,
        provider="dummy",
        external_id="abc123",
        error_message=None,
    )

    assert missive.status == MissiveStatus.SENT
    assert missive.provider == "dummy"
    assert missive.external_id == "abc123"
    assert missive.error_message is None
    assert missive.sent_at == frozen_clock()
    assert missive.save_calls == 1


def test_update_status_handles_delivered_and_read() -> None:
    missive = DummyMissive()
    provider = DummyProvider(missive=missive, clock=frozen_clock)

    provider._update_status(MissiveStatus.DELIVERED)
    assert missive.delivered_at == frozen_clock()

    provider._update_status(MissiveStatus.READ)
    assert missive.read_at == frozen_clock()


def test_create_event_invokes_logger() -> None:
    missive = DummyMissive()
    events: List[Dict[str, Any]] = []

    def logger(payload: Dict[str, Any]) -> None:
        events.append(payload)

    provider = DummyProvider(missive=missive, event_logger=logger, clock=frozen_clock)

    provider._create_event(
        "delivered", "Delivered successfully", MissiveStatus.DELIVERED
    )

    assert len(events) == 1
    event = events[0]
    assert event["provider"] == "Dummy"
    assert event["event_type"] == "delivered"
    assert event["description"] == "Delivered successfully"
    assert event["status"] == MissiveStatus.DELIVERED
    assert event["occurred_at"] == frozen_clock()
    assert event["metadata"] == {}


@pytest.mark.parametrize(
    "missive_type,is_registered,requires_signature,expected",
    [
        ("EMAIL", False, False, "email"),
        ("EMAIL", True, False, "email_ar"),
        ("POSTAL", False, False, "postal"),
        ("POSTAL", True, False, "postal_registered"),
        ("POSTAL", True, True, "postal_signature"),
        ("POSTAL_REGISTERED", False, False, "postal_registered"),
        ("POSTAL_REGISTERED", False, True, "postal_signature"),
        ("SMS", False, False, "sms"),
        ("BRANDED", False, False, DummyProvider.name.lower()),
        ("RCS", False, False, "rcs"),
        ("LRE", False, False, "lre"),
    ],
)
def test_detect_service_type(
    missive_type: str, is_registered: bool, requires_signature: bool, expected: str
) -> None:
    missive = DummyMissive()
    missive.missive_type = missive_type
    missive.is_registered = is_registered
    missive.requires_signature = requires_signature

    provider = DummyProvider(missive=missive)

    assert provider._detect_service_type() == expected


def test_list_available_proofs_flags_supported_services() -> None:
    missive = DummyMissive()
    missive.missive_type = "POSTAL"
    missive.is_registered = True

    provider = DummyProvider(missive=missive)
    proofs = provider.list_available_proofs()

    assert proofs == {"postal_registered": True}


def test_get_service_status_default_information() -> None:
    provider = DummyProvider(clock=frozen_clock)
    status = provider.get_service_status()

    assert status["status"] == "unknown"
    assert status["services"] == DummyProvider.services
    assert status["last_check"] == frozen_clock()
    assert "warnings" in status
