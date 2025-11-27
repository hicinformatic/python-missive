"""Maps.co Geocoding API address verification backend."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, cast

import requests

from .base import BaseAddressBackend


class MapsCoAddressBackend(BaseAddressBackend):
    """Maps.co Geocoding API backend for address verification.

    Maps.co provides forward and reverse geocoding based on OpenStreetMap data
    using the Nominatim geocoding engine.
    Free tier: Limited requests/day (check documentation).
    Requires API key (free registration).
    """

    name = "maps_co"
    display_name = "Maps.co"
    config_keys = ["MAPS_CO_API_KEY", "MAPS_CO_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://geocode.maps.co/docs/"
    site_url = "https://geocode.maps.co"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Maps.co backend.

        Args:
            config: Optional configuration dict with:
                - MAPS_CO_API_KEY: API key (required)
                - MAPS_CO_BASE_URL: Custom base URL (default: official)
        """
        super().__init__(config)
        self._api_key = self._config.get("MAPS_CO_API_KEY")
        if not self._api_key:
            raise ValueError("MAPS_CO_API_KEY is required")
        self._base_url = self._config.get("MAPS_CO_BASE_URL", "https://geocode.maps.co")
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
        if address_line3:
            parts.append(address_line3)
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
        """Respect Maps.co rate limit (1 request per second to avoid 429)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < 1.0:  # 1 second delay
            time.sleep(1.0 - time_since_last)
        self._last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Maps.co API."""
        self._rate_limit()

        url = f"{self._base_url}{endpoint}"

        request_params: Dict[str, Any] = {"api_key": self._api_key, "format": "json"}
        if params:
            request_params.update(params)

        try:
            response = requests.get(url, params=request_params, timeout=10)
            response.raise_for_status()
            json_response = response.json()
            # Maps.co returns list for /search, dict for /reverse
            return json_response
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                return {"error": "Rate limit exceeded. Please wait and retry."}
            try:
                error_data = response.json()
                error_msg = error_data.get("error", str(e))
            except Exception:
                error_msg = str(e)
            return {"error": error_msg}
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def _extract_address_from_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Maps.co API result."""
        address = result.get("address", {})

        # Build address_line1 from house_number and road
        address_line1_parts = []
        if address.get("house_number"):
            address_line1_parts.append(str(address["house_number"]))
        if address.get("road"):
            address_line1_parts.append(address["road"])
        address_line1 = " ".join(address_line1_parts).strip()

        # Fallback to display_name if address_line1 is empty
        if not address_line1:
            display_name = result.get("display_name", "")
            if display_name:
                parts = display_name.split(",")
                if parts:
                    address_line1 = parts[0].strip()

        # Extract coordinates
        latitude = None
        longitude = None
        if "lat" in result and result["lat"]:
            try:
                latitude = float(result["lat"])
            except (ValueError, TypeError):
                pass
        if "lon" in result and result["lon"]:
            try:
                longitude = float(result["lon"])
            except (ValueError, TypeError):
                pass

        return {
            "address_line1": address_line1 or "",
            "address_line2": address.get("suburb", "") or address.get("neighbourhood", ""),
            "address_line3": address.get("quarter", ""),
            "city": (
                address.get("city", "")
                or address.get("town", "")
                or address.get("village", "")
                or address.get("municipality", "")
            ),
            "postal_code": address.get("postcode", ""),
            "state": address.get("state", "") or address.get("region", ""),
            "country": (
                address.get("country_code", "").upper() if address.get("country_code") else ""
            ),
            "address_reference": (
                str(result.get("place_id", "")) if result.get("place_id") else None
            ),
            "latitude": latitude,
            "longitude": longitude,
            "confidence": (
                0.8 if result.get("place_id") else 0.5
            ),  # Maps.co doesn't provide explicit confidence
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
        """Validate an address using Maps.co search API."""
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

        params: Dict[str, Any] = {"q": query_string, "limit": 5}
        if country:
            params["country"] = country.upper()

        result = self._make_request("/search", params)

        if "error" in result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": [result["error"]],
            }

        # Maps.co returns a list of results
        if not isinstance(result, list):
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Invalid response format"],
            }

        if not result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["No address found"],
            }

        best_match = result[0]
        normalized = self._extract_address_from_result(best_match)

        confidence = normalized.get("confidence", 0.0)
        is_valid = confidence >= 0.5

        suggestions = []
        if not is_valid and len(result) > 1:
            for item in result[1:5]:
                suggestion = self._extract_address_from_result(item)
                suggestions.append(
                    {
                        "formatted_address": item.get("display_name", ""),
                        "confidence": suggestion.get("confidence", 0.0),
                        "latitude": suggestion.get("latitude"),
                        "longitude": suggestion.get("longitude"),
                    }
                )

        warnings = []
        if confidence < 0.7:
            warnings.append("Low confidence match")

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
            "address_reference": normalized.get("address_reference"),
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
        """Geocode an address to coordinates using Maps.co."""
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

        params: Dict[str, Any] = {"q": query_string, "limit": 1}
        if country:
            params["country"] = country.upper()

        result = self._make_request("/search", params)

        if "error" in result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        if not isinstance(result, list) or not result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["No address found"],
            }

        best_match = result[0]
        normalized = self._extract_address_from_result(best_match)

        return {
            "latitude": normalized.get("latitude"),
            "longitude": normalized.get("longitude"),
            "accuracy": "ROOFTOP",  # Maps.co doesn't provide explicit accuracy
            "confidence": normalized.get("confidence", 0.0),
            "formatted_address": best_match.get("display_name", ""),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def reverse_geocode(self, latitude: float, longitude: float, **kwargs: Any) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Maps.co."""
        params: Dict[str, Any] = {"lat": latitude, "lon": longitude}
        if "language" in kwargs:
            params["accept-language"] = kwargs["language"]

        result = self._make_request("/reverse", params)

        if "error" in result:
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "latitude": latitude,
                "longitude": longitude,
                "confidence": 0.0,
                "address_reference": None,
                "errors": [result["error"]],
            }

        # Maps.co reverse geocoding returns a single result object (dict), not a list
        if not result or not isinstance(result, dict):
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "latitude": latitude,
                "longitude": longitude,
                "confidence": 0.0,
                "address_reference": None,
                "errors": ["Invalid response format"],
            }

        normalized = self._extract_address_from_result(result)

        return {
            **normalized,
            "formatted_address": result.get("display_name", ""),
            "latitude": normalized.get("latitude", latitude),
            "longitude": normalized.get("longitude", longitude),
            "confidence": normalized.get("confidence", 0.0),
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def get_address_by_reference(self, address_reference: str, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve address details by a reference ID using Maps.co.

        Maps.co uses Nominatim place_id for references.
        """
        # Maps.co doesn't have a direct lookup by place_id endpoint
        # We need to use the search with the place_id or use reverse geocoding
        # For now, we'll return an error as Maps.co doesn't support direct lookup
        return {
            "address_line1": None,
            "address_line2": None,
            "address_line3": None,
            "city": None,
            "postal_code": None,
            "state": None,
            "country": None,
            "formatted_address": None,
            "latitude": None,
            "longitude": None,
            "confidence": 0.0,
            "address_reference": address_reference,
            "errors": [
                "Maps.co API does not support direct lookup by place_id. "
                "Use reverse geocoding with coordinates instead."
            ],
        }
