"""LocationIQ address verification backend."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class LocationIQAddressBackend(BaseAddressBackend):
    """LocationIQ Geocoding API backend for address verification.

    Free tier: 5000 requests/day.
    Requires API key (free registration).
    """

    name = "locationiq"
    display_name = "LocationIQ"
    config_keys = ["LOCATIONIQ_API_KEY", "LOCATIONIQ_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://docs.locationiq.com/"
    site_url = "https://locationiq.com"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize LocationIQ backend.

        Args:
            config: Optional configuration dict with:
                - LOCATIONIQ_API_KEY: API key (required)
                - LOCATIONIQ_BASE_URL: Custom base URL (default: official)
        """
        super().__init__(config)
        self._api_key = self._config.get("LOCATIONIQ_API_KEY")
        if not self._api_key:
            raise ValueError("LOCATIONIQ_API_KEY is required")
        self._base_url = self._config.get("LOCATIONIQ_BASE_URL", "https://api.locationiq.com/v1")
        self._last_request_time = 0.0

    def _build_address_string(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
    ) -> str:
        """Build a query string from address components."""
        parts = []
        if address_line1:
            parts.append(address_line1)
        if address_line2:
            parts.append(address_line2)
        if city:
            parts.append(city)
        if postal_code:
            parts.append(postal_code)
        if state:
            parts.append(state)
        if country:
            parts.append(country)
        return ", ".join(filter(None, parts))

    def _rate_limit(self) -> None:
        """Respect rate limit (2 requests per second)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < 0.5:
            time.sleep(0.5 - time_since_last)
        self._last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the LocationIQ API."""
        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        self._rate_limit()

        url = f"{self._base_url}{endpoint}"

        request_params: Dict[str, Any] = {
            "key": self._api_key,
            "format": "json",
        }
        if params:
            request_params.update(params)

        try:
            response = requests.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def _extract_address_from_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a LocationIQ result."""
        address = result.get("address", {})

        # Extract address_line1
        address_line1 = ""
        if address.get("house_number") and address.get("road"):
            address_line1 = f"{address.get('house_number')} {address.get('road')}".strip()
        elif address.get("road"):
            address_line1 = address.get("road", "")
        elif result.get("display_name"):
            # Fallback: use first part of display_name
            display_name = result.get("display_name", "")
            parts = display_name.split(",")
            if parts:
                address_line1 = parts[0].strip()

        return {
            "address_line1": address_line1 or "",
            "address_line2": "",
            "address_line3": "",
            "city": address.get("city") or address.get("town") or address.get("village") or "",
            "postal_code": address.get("postcode", ""),
            "state": address.get("state") or address.get("region", ""),
            "country": (
                address.get("country_code", "").upper() if address.get("country_code") else ""
            ),
            "address_reference": str(result.get("place_id", "")),
        }

    def validate_address(
        self,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        address_line3: Optional[str] = None,
        city: Optional[str] = None,
        postal_code: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Validate an address using LocationIQ."""
        if query:
            query_string = query
        else:
            query_string = self._build_address_string(
                address_line1,
                address_line2,
                address_line3,
                city,
                postal_code,
                state,
                country,
            )

        if not query_string:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Address query is empty"],
            }

        params: Dict[str, Any] = {"q": query_string, "limit": 5, "addressdetails": 1}
        if country:
            params["countrycodes"] = country.lower()

        result = self._make_request("/search.php", params)

        if "error" in result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": [result["error"]],
            }

        # LocationIQ returns a list
        if isinstance(result, list):
            results = result
        else:
            results = [result] if result else []

        if not results:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["No address found"],
            }

        best_match = results[0]
        normalized = self._extract_address_from_result(best_match)

        # Extract coordinates
        lat = best_match.get("lat")
        lon = best_match.get("lon")
        if lat is not None and lon is not None:
            normalized["latitude"] = float(lat)
            normalized["longitude"] = float(lon)

        # LocationIQ provides importance score (0-1)
        importance = best_match.get("importance", 0.0)
        confidence = min(importance, 1.0)
        normalized["confidence"] = confidence

        is_valid = confidence >= 0.5

        suggestions = []
        if not is_valid and len(results) > 1:
            for result_item in results[1:5]:
                suggestion_normalized = self._extract_address_from_result(result_item)
                suggestion_lat = result_item.get("lat")
                suggestion_lon = result_item.get("lon")
                suggestion_importance = result_item.get("importance", 0.0)

                suggestion_data = {
                    "formatted_address": result_item.get("display_name", ""),
                    "confidence": min(suggestion_importance, 1.0),
                }
                if suggestion_lat is not None and suggestion_lon is not None:
                    suggestion_data["latitude"] = float(suggestion_lat)
                    suggestion_data["longitude"] = float(suggestion_lon)
                suggestion_data.update(suggestion_normalized)
                suggestions.append(suggestion_data)

        warnings = []
        if confidence < 0.7:
            warnings.append("Low confidence match")

        place_id = best_match.get("place_id")

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
            "address_reference": (
                str(place_id) if place_id is not None else normalized.get("address_reference")
            ),
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
        query: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Geocode an address to coordinates using LocationIQ."""
        if query:
            query_string = query
        else:
            query_string = self._build_address_string(
                address_line1,
                address_line2,
                address_line3,
                city,
                postal_code,
                state,
                country,
            )

        if not query_string:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["Address query is empty"],
            }

        params: Dict[str, Any] = {"q": query_string, "limit": 1, "addressdetails": 1}
        if country:
            params["countrycodes"] = country.lower()

        result = self._make_request("/search.php", params)

        if "error" in result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        if isinstance(result, list):
            results = result
        else:
            results = [result] if result else []

        if not results:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["No address found"],
            }

        feature = results[0]
        normalized = self._extract_address_from_result(feature)

        lat = feature.get("lat")
        lon = feature.get("lon")
        latitude = float(lat) if lat is not None else None
        longitude = float(lon) if lon is not None else None

        # Determine accuracy from address type
        address_type = feature.get("type", "")
        accuracy_map = {
            "house": "ROOFTOP",
            "building": "ROOFTOP",
            "address": "ROOFTOP",
            "street": "STREET",
            "city": "CITY",
            "town": "CITY",
            "village": "CITY",
        }
        accuracy = accuracy_map.get(address_type, "APPROXIMATE")

        importance = feature.get("importance", 0.0)
        confidence = min(importance, 1.0)

        place_id = feature.get("place_id")

        return {
            **normalized,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "confidence": confidence,
            "formatted_address": feature.get("display_name", ""),
            "address_reference": str(place_id) if place_id is not None else None,
            "errors": [],
        }

    def reverse_geocode(self, latitude: float, longitude: float, **kwargs: Any) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using LocationIQ."""
        params: Dict[str, Any] = {
            "lat": str(latitude),
            "lon": str(longitude),
            "addressdetails": 1,
        }
        if "language" in kwargs:
            params["accept-language"] = kwargs["language"]

        result = self._make_request("/reverse.php", params)

        if "error" in result:
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "latitude": None,
                "longitude": None,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        normalized = self._extract_address_from_result(result)
        normalized["latitude"] = latitude
        normalized["longitude"] = longitude

        return {
            **normalized,
            "formatted_address": result.get("display_name", ""),
            "errors": [],
        }

    def get_address_by_reference(self, address_reference: str, **kwargs: Any) -> Dict[str, Any]:
        """Get address by reference ID using LocationIQ.

        LocationIQ uses place_id for reverse lookup.
        We can use the reverse geocode with coordinates if available,
        or search with place_id.

        Note: LocationIQ doesn't have a direct lookup by place_id endpoint,
        so we'll need to use coordinates if they're stored with the reference.
        """
        # LocationIQ place_id format is numeric
        # Without a direct lookup endpoint, we return an error
        return {
            "address_line1": None,
            "address_line2": None,
            "address_line3": None,
            "city": None,
            "postal_code": None,
            "state": None,
            "country": None,
            "latitude": None,
            "longitude": None,
            "formatted_address": None,
            "errors": [
                "LocationIQ does not support direct lookup by reference ID. "
                "Use reverse_geocode with coordinates instead."
            ],
        }
