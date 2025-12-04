"""Tests for address verification backends."""

from __future__ import annotations

from typing import Dict

import pytest

try:
    from geoaddress import Address, BaseAddressBackend
except ImportError:
    from pymissive.address import Address
    from pymissive.address_backends import (BaseAddressBackend,
                                             GoogleMapsAddressBackend,
                                             HereAddressBackend,
                                             MapboxAddressBackend,
                                             NominatimAddressBackend,
                                             PhotonAddressBackend)
from pymissive.helpers import (describe_address_backends,
                                    get_address_backends_from_config)
from tests.test_config import (MISSIVE_CONFIG_ADDRESS_BACKENDS,
                               get_working_address_backend)


@pytest.fixture
def test_address() -> Dict[str, str]:
    """Provide a standard test address."""
    return {
        "address_line1": "123 Main Street",
        "city": "Paris",
        "postal_code": "75001",
        "country": "FR",
    }


@pytest.fixture
def real_address() -> Dict[str, str]:
    """Provide a real address for testing (Eiffel Tower area)."""
    return {
        "address_line1": "Champ de Mars",
        "city": "Paris",
        "postal_code": "75007",
        "country": "FR",
    }


class TestBaseAddressBackend:
    """Test the base address backend."""

    def test_base_backend_initialization(self):
        """Test base backend can be instantiated."""
        backend = BaseAddressBackend()
        assert backend.name == "base"
        assert isinstance(backend.config, dict)

    def test_base_backend_normalize_address(self, test_address):
        """Test base backend normalize_address method."""
        backend = BaseAddressBackend()
        result = backend.normalize_address(**test_address)

        assert "address_line1" in result
        assert "city" in result
        assert "postal_code" in result
        assert "country" in result
        assert "formatted_address" in result
        assert "123 Main Street" in result["formatted_address"]
        assert "Paris" in result["formatted_address"]

    def test_base_backend_validate_address_not_implemented(self, test_address):
        """Test base backend validate_address returns not implemented."""
        backend = BaseAddressBackend()
        result = backend.validate_address(**test_address)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert (
            "not implement" in result["errors"][0].lower()
            or "does not implement" in result["errors"][0].lower()
        )

    def test_base_backend_geocode_not_implemented(self, test_address):
        """Test base backend geocode returns not implemented."""
        backend = BaseAddressBackend()
        result = backend.geocode(**test_address)

        assert result["latitude"] is None
        assert result["longitude"] is None
        assert len(result["errors"]) > 0

    def test_base_backend_reverse_geocode_not_implemented(self):
        """Test base backend reverse_geocode returns not implemented."""
        backend = BaseAddressBackend()
        result = backend.reverse_geocode(48.8566, 2.3522)

        assert result["address_line1"] is None
        assert len(result["errors"]) > 0

    def test_base_backend_check_package_and_config(self):
        """Test base backend check_package_and_config."""
        backend = BaseAddressBackend()
        result = backend.check_package_and_config()

        assert "packages" in result
        assert "config" in result
        assert isinstance(result["packages"], dict)
        assert isinstance(result["config"], dict)


class TestAddressBackendDisplayName:
    """Tests for human-readable backend names."""

    def test_base_backend_label_defaults_to_title_case(self):
        backend = BaseAddressBackend()
        assert backend.label == "Base"

    def test_describe_address_backends_includes_display_name(self):
        payload = describe_address_backends(
            [
                {
                    "class": "pymissive.address_backends.nominatim.NominatimAddressBackend",
                    "config": {},
                }
            ],
            skip_api_test=True,
        )
        assert payload["items"][0]["backend_display_name"] == "OpenStreetMap Nominatim"


class TestAddressModel:
    """Unit tests for the Address dataclass."""

    def test_from_dict_and_to_dict(self):
        payload = {
            "line1": "1600 Amphitheatre Parkway",
            "line2": "Bâtiment 2",
            "postal_code": "94043",
            "city": "Mountain View",
            "country": "US",
            "latitude": 37.4221,
            "longitude": -122.0841,
            "formatted_address": "1600 Amphitheatre Parkway, 94043 Mountain View, US",
            "backend_used": "google_maps",
            "backend_reference": "gmaps:place:123",
        }
        address = Address.from_dict(payload)
        assert address.line1 == payload["line1"]
        assert address.city == "Mountain View"
        assert address.backend_reference == "gmaps:place:123"
        serialized = address.to_dict()
        assert serialized["line1"] == payload["line1"]
        assert serialized["city"] == payload["city"]
        assert serialized["backend_reference"] == "gmaps:place:123"

    def test_normalize_with_backends(self, real_address):
        normalized, payload = Address.normalize_with_backends(
            MISSIVE_CONFIG_ADDRESS_BACKENDS,
            **real_address,
        )
        assert isinstance(normalized, Address)
        assert payload or normalized.line1
        # When a backend is available we should either get a backend name or warnings
        if payload.get("backend_used"):
            assert normalized.backend_used == payload["backend_used"]
        if payload.get("backend_reference"):
            assert normalized.backend_reference == payload["backend_reference"]


class TestNominatimAddressBackend:
    """Test Nominatim address backend."""

    def test_nominatim_initialization(self):
        """Test Nominatim backend can be instantiated."""
        backend = NominatimAddressBackend()
        assert backend.name == "nominatim"
        assert backend._base_url == "https://nominatim.openstreetmap.org"

    def test_nominatim_check_package_and_config(self):
        """Test Nominatim backend package and config check."""
        backend = NominatimAddressBackend()
        result = backend.check_package_and_config()

        assert result["packages"]["requests"] == "installed"
        assert "NOMINATIM_USER_AGENT" in result["config"]
        assert "NOMINATIM_BASE_URL" in result["config"]

    def test_nominatim_normalize_address(self, test_address):
        """Test Nominatim backend normalize_address."""
        backend = NominatimAddressBackend()
        result = backend.normalize_address(**test_address)

        assert "formatted_address" in result
        assert "123 Main Street" in result["formatted_address"]

    def test_nominatim_validate_address_real(self, real_address):
        """Test Nominatim backend validate_address with real address."""
        backend = NominatimAddressBackend()
        result = backend.validate_address(**real_address)

        assert "is_valid" in result
        assert "confidence" in result
        assert "normalized_address" in result
        assert isinstance(result["confidence"], (int, float))

    def test_nominatim_geocode_real(self, real_address):
        """Test Nominatim backend geocode with real address."""
        backend = NominatimAddressBackend()
        result = backend.geocode(**real_address)

        # Should return coordinates if address is found
        if result.get("latitude") is not None:
            assert isinstance(result["latitude"], (int, float))
            assert isinstance(result["longitude"], (int, float))
            assert -90 <= result["latitude"] <= 90
            assert -180 <= result["longitude"] <= 180

    def test_nominatim_rate_limiting(self):
        """Test Nominatim backend respects rate limiting."""
        backend = NominatimAddressBackend()
        import time

        start_time = time.time()
        backend._rate_limit()
        backend._rate_limit()
        elapsed = time.time() - start_time

        # Should take at least 1 second between requests
        assert elapsed >= 1.0


class TestPhotonAddressBackend:
    """Test Photon address backend."""

    def test_photon_initialization(self):
        """Test Photon backend can be instantiated."""
        backend = PhotonAddressBackend()
        assert backend.name == "photon"
        assert backend._base_url == "https://photon.komoot.io"

    def test_photon_check_package_and_config(self):
        """Test Photon backend package and config check."""
        backend = PhotonAddressBackend()
        result = backend.check_package_and_config()

        assert result["packages"]["requests"] == "installed"
        assert "PHOTON_BASE_URL" in result["config"]

    def test_photon_normalize_address(self, test_address):
        """Test Photon backend normalize_address."""
        backend = PhotonAddressBackend()
        result = backend.normalize_address(**test_address)

        assert "formatted_address" in result
        assert "123 Main Street" in result["formatted_address"]

    def test_photon_validate_address_real(self, real_address):
        """Test Photon backend validate_address with real address."""
        backend = PhotonAddressBackend()
        result = backend.validate_address(**real_address)

        assert "is_valid" in result
        assert "confidence" in result
        assert "normalized_address" in result
        assert isinstance(result["confidence"], (int, float))

    def test_photon_geocode_real(self, real_address):
        """Test Photon backend geocode with real address."""
        backend = PhotonAddressBackend()
        result = backend.geocode(**real_address)

        # Should return coordinates if address is found
        if result.get("latitude") is not None:
            assert isinstance(result["latitude"], (int, float))
            assert isinstance(result["longitude"], (int, float))
            assert -90 <= result["latitude"] <= 90
            assert -180 <= result["longitude"] <= 180


class TestGoogleMapsAddressBackend:
    """Test Google Maps address backend."""

    def test_google_maps_initialization(self):
        """Test Google Maps backend can be instantiated."""
        backend = GoogleMapsAddressBackend()
        assert backend.name == "google_maps"

    def test_google_maps_check_package_and_config(self):
        """Test Google Maps backend package and config check."""
        backend = GoogleMapsAddressBackend()
        result = backend.check_package_and_config()

        assert result["packages"]["requests"] == "installed"
        assert "GOOGLE_MAPS_API_KEY" in result["config"]

    def test_google_maps_validate_address_no_key(self, test_address):
        """Test Google Maps backend validate_address without API key."""
        backend = GoogleMapsAddressBackend()
        result = backend.validate_address(**test_address)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert "not configured" in result["errors"][0].lower()

    def test_google_maps_normalize_address(self, test_address):
        """Test Google Maps backend normalize_address."""
        backend = GoogleMapsAddressBackend()
        result = backend.normalize_address(**test_address)

        assert "formatted_address" in result
        assert "123 Main Street" in result["formatted_address"]


class TestMapboxAddressBackend:
    """Test Mapbox address backend."""

    def test_mapbox_initialization(self):
        """Test Mapbox backend can be instantiated."""
        backend = MapboxAddressBackend()
        assert backend.name == "mapbox"

    def test_mapbox_check_package_and_config(self):
        """Test Mapbox backend package and config check."""
        backend = MapboxAddressBackend()
        result = backend.check_package_and_config()

        assert result["packages"]["requests"] == "installed"
        assert "MAPBOX_ACCESS_TOKEN" in result["config"]

    def test_mapbox_validate_address_no_token(self, test_address):
        """Test Mapbox backend validate_address without access token."""
        backend = MapboxAddressBackend()
        result = backend.validate_address(**test_address)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert "not configured" in result["errors"][0].lower()

    def test_mapbox_normalize_address(self, test_address):
        """Test Mapbox backend normalize_address."""
        backend = MapboxAddressBackend()
        result = backend.normalize_address(**test_address)

        assert "formatted_address" in result
        assert "123 Main Street" in result["formatted_address"]


class TestHereAddressBackend:
    """Test HERE address backend."""

    def test_here_initialization(self):
        """Test HERE backend can be instantiated."""
        backend = HereAddressBackend()
        assert backend.name == "here"

    def test_here_check_package_and_config(self):
        """Test HERE backend package and config check."""
        backend = HereAddressBackend()
        result = backend.check_package_and_config()

        assert result["packages"]["requests"] == "installed"
        assert "HERE_APP_ID" in result["config"]
        assert "HERE_APP_CODE" in result["config"]

    def test_here_validate_address_no_credentials(self, test_address):
        """Test HERE backend validate_address without credentials."""
        backend = HereAddressBackend()
        result = backend.validate_address(**test_address)

        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert "must be configured" in result["errors"][0].lower()

    def test_here_normalize_address(self, test_address):
        """Test HERE backend normalize_address."""
        backend = HereAddressBackend()
        result = backend.normalize_address(**test_address)

        assert "formatted_address" in result
        assert "123 Main Street" in result["formatted_address"]


class TestAddressBackendFallback:
    """Test address backend fallback mechanism."""

    def test_get_address_backends_from_config(self):
        """Test get_address_backends_from_config loads backends."""
        backends = get_address_backends_from_config(MISSIVE_CONFIG_ADDRESS_BACKENDS)

        # Should find at least one backend (Nominatim or Photon should work)
        assert len(backends) > 0
        assert all(isinstance(b, BaseAddressBackend) for b in backends)

    def test_get_working_address_backend(self):
        """Test get_working_address_backend finds a working backend."""
        backend = get_working_address_backend()

        # Should find at least one backend (Nominatim or Photon should work)
        assert backend is not None
        assert isinstance(backend, BaseAddressBackend)

    def test_get_working_address_backend_with_test_address(self, test_address):
        """Test get_working_address_backend with custom test address."""
        backend = get_working_address_backend(test_address=test_address)

        # Should find at least one backend
        assert backend is not None
        assert isinstance(backend, BaseAddressBackend)

    def test_working_backend_can_validate(self, real_address):
        """Test that working backend can validate addresses."""
        backend = get_working_address_backend()

        if backend:
            result = backend.validate_address(**real_address)
            assert "is_valid" in result
            assert "confidence" in result
            assert isinstance(result["confidence"], (int, float))

    def test_working_backend_can_geocode(self, real_address):
        """Test that working backend can geocode addresses."""
        backend = get_working_address_backend()

        if backend:
            result = backend.geocode(**real_address)
            # May or may not find coordinates, but should not error
            assert "latitude" in result
            assert "longitude" in result
            assert "errors" in result

    def test_working_backend_can_normalize(self, test_address):
        """Test that working backend can normalize addresses."""
        backend = get_working_address_backend()

        if backend:
            result = backend.normalize_address(**test_address)
            assert "formatted_address" in result
            assert "address_line1" in result
            assert "city" in result
