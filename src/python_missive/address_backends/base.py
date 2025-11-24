"""Base address verification backend."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class BaseAddressBackend:
    """Base class for address verification backends.

    Provides a generic interface for address validation, geocoding,
    and normalization across different providers.
    """

    name: str = "base"
    config_keys: List[str] = []
    required_packages: List[str] = []
    documentation_url: Optional[str] = None
    site_url: Optional[str] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the backend with optional configuration.

        Args:
            config: Configuration dictionary with backend-specific keys.
        """
        self._raw_config: Dict[str, Any] = dict(config or {})
        self._config: Dict[str, Any] = self._filter_config(self._raw_config)

    def _filter_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the subset of config keys declared by the backend."""
        if not self.config_keys:
            return dict(config)
        return {k: v for k, v in config.items() if k in self.config_keys}

    @property
    def config(self) -> Dict[str, Any]:
        """Access configuration values."""
        return self._config

    def validate_address(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Validate an address and return normalized/verified data.

        Args:
            address_line1: Street number and name.
            address_line2: Building, apartment, floor (optional).
            address_line3: Additional address info (optional).
            city: City name.
            postal_code: Postal/ZIP code.
            state: State/region/province.
            country: ISO country code (e.g., "FR", "US", "GB").
            **kwargs: Additional address fields.

        Returns:
            Dictionary with validation results:
            - is_valid (bool): Whether the address is valid.
            - normalized_address (dict): Normalized address components.
            - confidence (float): Confidence score (0.0-1.0).
            - suggestions (list): List of suggested addresses if validation fails.
            - warnings (list): List of warnings about the address.
            - errors (list): List of errors if validation fails.
        """
        return {
            "is_valid": False,
            "normalized_address": {},
            "confidence": 0.0,
            "suggestions": [],
            "warnings": ["validate_address() not implemented"],
            "errors": ["Backend does not implement address validation"],
        }

    def geocode(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Geocode an address to coordinates (latitude, longitude).

        Args:
            address_line1: Street number and name.
            address_line2: Building, apartment, floor (optional).
            address_line3: Additional address info (optional).
            city: City name.
            postal_code: Postal/ZIP code.
            state: State/region/province.
            country: ISO country code (e.g., "FR", "US", "GB").
            **kwargs: Additional address fields.

        Returns:
            Dictionary with geocoding results:
            - latitude (float): Latitude coordinate.
            - longitude (float): Longitude coordinate.
            - accuracy (str): Accuracy level (e.g., "ROOFTOP", "STREET", "CITY").
            - confidence (float): Confidence score (0.0-1.0).
            - formatted_address (str): Formatted address string.
        """
        return {
            "latitude": None,
            "longitude": None,
            "accuracy": None,
            "confidence": 0.0,
            "formatted_address": None,
            "errors": ["geocode() not implemented"],
        }

    def reverse_geocode(
        self, latitude: float, longitude: float, **kwargs: Any
    ) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address.

        Args:
            latitude: Latitude coordinate.
            longitude: Longitude coordinate.
            **kwargs: Additional options (e.g., language, country bias).

        Returns:
            Dictionary with reverse geocoding results:
            - address_line1 (str): Street number and name.
            - address_line2 (str): Building, apartment, floor (optional).
            - city (str): City name.
            - postal_code (str): Postal/ZIP code.
            - state (str): State/region/province.
            - country (str): ISO country code.
            - formatted_address (str): Formatted address string.
            - confidence (float): Confidence score (0.0-1.0).
        """
        return {
            "address_line1": None,
            "address_line2": None,
            "city": None,
            "postal_code": None,
            "state": None,
            "country": None,
            "formatted_address": None,
            "confidence": 0.0,
            "errors": ["reverse_geocode() not implemented"],
        }

    def normalize_address(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Normalize address components to standard format.

        Args:
            address_line1: Street number and name.
            address_line2: Building, apartment, floor (optional).
            address_line3: Additional address info (optional).
            city: City name.
            postal_code: Postal/ZIP code.
            state: State/region/province.
            country: ISO country code (e.g., "FR", "US", "GB").
            **kwargs: Additional address fields.

        Returns:
            Dictionary with normalized address components:
            - address_line1 (str): Normalized street address.
            - address_line2 (str): Normalized building/apartment info.
            - city (str): Normalized city name.
            - postal_code (str): Normalized postal code.
            - state (str): Normalized state/region.
            - country (str): ISO country code.
            - formatted_address (str): Complete formatted address.
        """
        return {
            "address_line1": address_line1 or "",
            "address_line2": address_line2 or "",
            "address_line3": address_line3 or "",
            "city": city or "",
            "postal_code": postal_code or "",
            "state": state or "",
            "country": country or "",
            "formatted_address": self._format_address(
                address_line1, address_line2, city, postal_code, state, country
            ),
        }

    def _format_address(
        self,
        address_line1: Optional[str],
        address_line2: Optional[str],
        city: Optional[str],
        postal_code: Optional[str],
        state: Optional[str],
        country: Optional[str],
    ) -> str:
        """Format address components into a single string."""
        parts = []
        if address_line1:
            parts.append(address_line1)
        if address_line2:
            parts.append(address_line2)
        city_line = []
        if postal_code:
            city_line.append(postal_code)
        if city:
            city_line.append(city)
        if city_line:
            parts.append(" ".join(city_line))
        if state:
            parts.append(state)
        if country:
            parts.append(country)
        return ", ".join(parts)

    def check_package_and_config(self) -> Dict[str, Any]:
        """Check if required packages are installed and config is valid.

        Returns:
            Dictionary with:
            - packages (dict): Status of required packages.
            - config (dict): Status of configuration keys.
        """
        import importlib

        packages = {}
        for pkg in self.required_packages:
            try:
                importlib.import_module(pkg)
                packages[pkg] = "installed"
            except ImportError:
                packages[pkg] = "missing"

        config_status = {}
        for key in self.config_keys:
            config_status[key] = "present" if key in self._config else "missing"

        return {
            "packages": packages,
            "config": config_status,
        }
