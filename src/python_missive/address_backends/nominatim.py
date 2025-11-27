"""Nominatim (OpenStreetMap) address verification backend."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class NominatimAddressBackend(BaseAddressBackend):
    """Nominatim (OpenStreetMap) Geocoding API backend for address verification.

    Completely free, no API key required. Uses OpenStreetMap data.
    Rate limit: 1 request per second (respected automatically).
    """

    name = "nominatim"
    display_name = "OpenStreetMap Nominatim"
    config_keys = ["NOMINATIM_BASE_URL", "NOMINATIM_USER_AGENT"]
    required_packages = ["requests"]
    documentation_url = "https://nominatim.org/release-docs/develop/api/Overview/"
    site_url = "https://nominatim.org"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Nominatim backend.

        Args:
            config: Optional configuration dict with:
                - NOMINATIM_BASE_URL: Custom Nominatim server URL (default: official)
                - NOMINATIM_USER_AGENT: User agent string (required by ToS)
        """
        super().__init__(config)
        self._base_url = self._config.get(
            "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
        )
        self._user_agent = self._config.get(
            "NOMINATIM_USER_AGENT", "python-missive/1.0"
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
        """Respect Nominatim rate limit (1 request per second)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)
        self._last_request_time = time.time()

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Nominatim API."""
        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        self._rate_limit()

        url = f"{self._base_url}{endpoint}"

        request_params: Dict[str, Any] = {
            "format": "json",
            "addressdetails": 1,
            "limit": 5,
        }
        if params:
            request_params.update(params)

        headers = {"User-Agent": self._user_agent}

        try:
            response = requests.get(
                url, params=request_params, headers=headers, timeout=10
            )
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())
        except requests.exceptions.HTTPError as e:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", str(e))
            except Exception:
                error_msg = str(e)
            return {"error": error_msg}
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

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
        """Validate an address using Nominatim."""
        # Si query est fourni, l'utiliser directement (priorité sur les composants)
        if query:
            query_string = query
        else:
            # Fallback sur les composants structurés si query n'est pas fourni
            query_string = self._build_address_string(
                address_line1,
                address_line2,
                address_line3,
                city,
                postal_code,
                state,
                country,
            )

        if not query:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Address query is empty"],
            }

        params = {"q": query_string}
        if country:
            params["countrycodes"] = country.lower()

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

        if not isinstance(result, list) or not result:
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

        lat = best_match.get("lat")
        lon = best_match.get("lon")
        if lat and lon:
            normalized["latitude"] = float(lat)
            normalized["longitude"] = float(lon)

        importance = best_match.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)
        is_valid = confidence >= 0.5 and importance >= 0.3

        suggestions = []
        if not is_valid and len(result) > 1:
            for item in result[1:5]:
                item_importance = item.get("importance", 0.0)
                suggestion_data = {
                    "formatted_address": item.get("display_name", ""),
                    "confidence": min(item_importance * 2.0, 1.0),
                }
                item_lat = item.get("lat")
                item_lon = item.get("lon")
                if item_lat and item_lon:
                    suggestion_data["latitude"] = float(item_lat)
                    suggestion_data["longitude"] = float(item_lon)
                suggestions.append(suggestion_data)

        warnings = []
        if importance < 0.5:
            warnings.append("Low importance match")
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
                str(place_id) if place_id else normalized.get("address_reference")
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
        """Geocode an address to coordinates using Nominatim."""
        # Si query est fourni, l'utiliser directement (priorité sur les composants)
        if query:
            query_string = query
        else:
            # Fallback sur les composants structurés si query n'est pas fourni
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

        params = {"q": query_string, "limit": 1}
        if country:
            params["countrycodes"] = country.lower()

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

        best_result = result[0]
        lat = best_result.get("lat")
        lon = best_result.get("lon")

        class_type = best_result.get("class", "")
        accuracy_map = {
            "house": "ROOFTOP",
            "building": "ROOFTOP",
            "place": "STREET",
            "highway": "STREET",
            "amenity": "STREET",
            "boundary": "CITY",
            "administrative": "CITY",
        }
        accuracy = accuracy_map.get(class_type, "UNKNOWN")

        importance = best_result.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        place_id = best_result.get("place_id")

        return {
            "latitude": float(lat) if lat else None,
            "longitude": float(lon) if lon else None,
            "accuracy": accuracy,
            "confidence": confidence,
            "formatted_address": best_result.get("display_name", ""),
            "address_reference": str(place_id) if place_id else None,
            "errors": [],
        }

    def reverse_geocode(
        self, latitude: float, longitude: float, **kwargs: Any
    ) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Nominatim."""
        params = {"lat": str(latitude), "lon": str(longitude)}
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
                "confidence": 0.0,
                "errors": [result["error"]],
            }

        if not isinstance(result, dict):
            return {
                "address_line1": None,
                "address_line2": None,
                "address_line3": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "confidence": 0.0,
                "errors": ["No address found"],
            }

        normalized = self._extract_address_from_result(result)

        lat = result.get("lat")
        lon = result.get("lon")
        if lat and lon:
            normalized["latitude"] = float(lat)
            normalized["longitude"] = float(lon)

        importance = result.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)
        place_id = result.get("place_id")

        return {
            **normalized,
            "formatted_address": result.get("display_name", ""),
            "confidence": confidence,
            "address_reference": (
                str(place_id) if place_id else normalized.get("address_reference")
            ),
            "errors": [],
        }

    def get_address_by_reference(
        self, address_reference: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Retrieve an address by its place_id using Nominatim lookup endpoint."""
        if not address_reference:
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
                "errors": ["address_reference is required"],
            }

        try:
            place_id = int(address_reference)
        except (ValueError, TypeError):
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
                "errors": ["Invalid place_id format"],
            }

        params = {"place_id": place_id, "format": "json", "addressdetails": 1}
        if "language" in kwargs:
            params["accept-language"] = kwargs["language"]

        result = self._make_request("/lookup", params)

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
                "latitude": None,
                "longitude": None,
                "confidence": 0.0,
                "address_reference": address_reference,
                "errors": [result["error"]],
            }

        if not isinstance(result, list) or not result:
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
                "errors": ["No address found for this place_id"],
            }

        address_result = result[0]
        normalized = self._extract_address_from_result(address_result)

        lat = address_result.get("lat")
        lon = address_result.get("lon")
        importance = address_result.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        return {
            **normalized,
            "formatted_address": address_result.get("display_name", ""),
            "latitude": float(lat) if lat else None,
            "longitude": float(lon) if lon else None,
            "confidence": confidence,
            "address_reference": address_reference,
            "errors": [],
        }

    def _extract_address_from_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Nominatim result."""
        address = result.get("address", {})

        address_line1 = ""
        house_number = address.get("house_number", "")
        road = address.get("road", "")
        if house_number and road:
            address_line1 = f"{house_number} {road}".strip()
        elif road:
            address_line1 = road

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or ""
        )
        postal_code = address.get("postcode", "")
        state = (
            address.get("state")
            or address.get("region")
            or address.get("province")
            or ""
        )
        country = address.get("country_code", "").upper()

        # Extract place_id for reverse lookup
        place_id = result.get("place_id")

        return {
            "address_line1": address_line1,
            "address_line2": "",
            "address_line3": "",
            "city": city,
            "postal_code": postal_code,
            "state": state,
            "country": country,
            "address_reference": str(place_id) if place_id else None,
        }
