"""OpenCage Geocoding API address verification backend."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class OpenCageAddressBackend(BaseAddressBackend):
    """OpenCage Geocoding API backend for address verification.

    Free tier: 5000 requests/day.
    Requires API key (free registration).
    """

    name = "opencage"
    display_name = "OpenCage"
    config_keys = ["OPENCAGE_API_KEY", "OPENCAGE_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://opencagedata.com/api"
    site_url = "https://opencagedata.com"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize OpenCage backend.

        Args:
            config: Optional configuration dict with:
                - OPENCAGE_API_KEY: API key (required)
                - OPENCAGE_BASE_URL: Custom base URL (default: official)
        """
        super().__init__(config)
        self._api_key = self._config.get("OPENCAGE_API_KEY")
        if not self._api_key:
            raise ValueError("OPENCAGE_API_KEY is required")
        self._base_url = self._config.get(
            "OPENCAGE_BASE_URL", "https://api.opencagedata.com/geocode/v1"
        )
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
        """Make a request to the OpenCage API."""
        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        self._rate_limit()

        url = f"{self._base_url}{endpoint}"

        request_params: Dict[str, Any] = {
            "key": self._api_key,
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
        """Extract address components from an OpenCage result."""
        components = result.get("components", {})

        # Extract address_line1
        address_line1 = ""
        if components.get("house_number") and components.get("road"):
            address_line1 = f"{components.get('house_number')} {components.get('road')}".strip()
        elif components.get("road"):
            address_line1 = components.get("road", "")
        elif result.get("formatted"):
            # Fallback: use first part of formatted address
            formatted = result.get("formatted", "")
            parts = formatted.split(",")
            if parts:
                address_line1 = parts[0].strip()

        # Extract city (try multiple fields)
        city = (
            components.get("city")
            or components.get("town")
            or components.get("village")
            or components.get("municipality")
            or ""
        )

        # Extract state/region
        state = (
            components.get("state")
            or components.get("region")
            or components.get("state_district")
            or ""
        )

        # Extract country code
        country_code = (
            components.get("country_code", "").upper() if components.get("country_code") else ""
        )

        return {
            "address_line1": address_line1 or "",
            "address_line2": "",
            "address_line3": "",
            "city": city,
            "postal_code": components.get("postcode", ""),
            "state": state,
            "country": country_code,
            "address_reference": str(result.get("annotations", {}).get("geohash", "")),
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
        """Validate an address using OpenCage."""
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

        params: Dict[str, Any] = {"q": query_string, "limit": 5, "no_annotations": 0}
        if country:
            params["countrycode"] = country.lower()
        if "language" in kwargs:
            params["language"] = kwargs["language"]

        result = self._make_request("/json", params)

        if "error" in result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": [result["error"]],
            }

        results = result.get("results", [])
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

        # Extract coordinates from geometry
        geometry = best_match.get("geometry", {})
        lat = geometry.get("lat")
        lon = geometry.get("lng")
        if lat is not None and lon is not None:
            normalized["latitude"] = float(lat)
            normalized["longitude"] = float(lon)

        # OpenCage provides confidence (0-10, we normalize to 0-1)
        confidence_raw = best_match.get("confidence", 0)
        confidence = min(confidence_raw / 10.0, 1.0)
        normalized["confidence"] = confidence

        is_valid = confidence >= 0.5

        suggestions = []
        if not is_valid and len(results) > 1:
            for result_item in results[1:5]:
                suggestion_normalized = self._extract_address_from_result(result_item)
                suggestion_geometry = result_item.get("geometry", {})
                suggestion_lat = suggestion_geometry.get("lat")
                suggestion_lon = suggestion_geometry.get("lng")
                suggestion_confidence_raw = result_item.get("confidence", 0)

                suggestion_data = {
                    "formatted_address": result_item.get("formatted", ""),
                    "confidence": min(suggestion_confidence_raw / 10.0, 1.0),
                }
                if suggestion_lat is not None and suggestion_lon is not None:
                    suggestion_data["latitude"] = float(suggestion_lat)
                    suggestion_data["longitude"] = float(suggestion_lon)
                suggestion_data.update(suggestion_normalized)
                suggestions.append(suggestion_data)

        warnings = []
        if confidence < 0.7:
            warnings.append("Low confidence match")

        # Use geohash as reference (or formatted address hash)
        address_reference = best_match.get("annotations", {}).get("geohash", "")

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
            "address_reference": (
                str(address_reference) if address_reference else normalized.get("address_reference")
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
        """Geocode an address to coordinates using OpenCage."""
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

        params: Dict[str, Any] = {"q": query_string, "limit": 1, "no_annotations": 0}
        if country:
            params["countrycode"] = country.lower()
        if "language" in kwargs:
            params["language"] = kwargs["language"]

        result = self._make_request("/json", params)

        if "error" in result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        results = result.get("results", [])
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

        geometry = feature.get("geometry", {})
        lat = geometry.get("lat")
        lon = geometry.get("lng")
        latitude = float(lat) if lat is not None else None
        longitude = float(lon) if lon is not None else None

        # Determine accuracy from components
        components = feature.get("components", {})
        accuracy = "APPROXIMATE"
        if components.get("house_number"):
            accuracy = "ROOFTOP"
        elif components.get("road"):
            accuracy = "STREET"
        elif components.get("city") or components.get("town"):
            accuracy = "CITY"

        # OpenCage provides confidence (0-10, normalize to 0-1)
        confidence_raw = feature.get("confidence", 0)
        confidence = min(confidence_raw / 10.0, 1.0)

        address_reference = feature.get("annotations", {}).get("geohash", "")

        return {
            **normalized,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "confidence": confidence,
            "formatted_address": feature.get("formatted", ""),
            "address_reference": str(address_reference) if address_reference else None,
            "errors": [],
        }

    def reverse_geocode(self, latitude: float, longitude: float, **kwargs: Any) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using OpenCage."""
        params: Dict[str, Any] = {
            "q": f"{latitude},{longitude}",
            "no_annotations": 0,
        }
        if "language" in kwargs:
            params["language"] = kwargs["language"]

        result = self._make_request("/json", params)

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

        results = result.get("results", [])
        if not results:
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
                "errors": ["No address found"],
            }

        best_match = results[0]
        normalized = self._extract_address_from_result(best_match)
        normalized["latitude"] = latitude
        normalized["longitude"] = longitude

        return {
            **normalized,
            "formatted_address": best_match.get("formatted", ""),
            "errors": [],
        }

    def get_address_by_reference(self, address_reference: str, **kwargs: Any) -> Dict[str, Any]:
        """Get address by reference ID using OpenCage.

        OpenCage uses geohash as reference.
        We can use reverse geocode with coordinates decoded from geohash.
        However, OpenCage doesn't have a direct lookup by geohash endpoint.
        """
        # OpenCage doesn't support direct lookup by geohash
        # We would need to decode geohash to coordinates and use reverse_geocode
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
                "OpenCage does not support direct lookup by reference ID. "
                "Use reverse_geocode with coordinates instead."
            ],
        }
