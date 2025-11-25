"""HERE address verification backend."""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class HereAddressBackend(BaseAddressBackend):
    """HERE Geocoding API backend for address verification.

    Requires the `requests` package and HERE API credentials (app_id and app_code).
    """

    name = "here"
    config_keys = ["HERE_APP_ID", "HERE_APP_CODE"]
    required_packages = ["requests"]
    documentation_url = "https://developer.here.com/documentation/geocoding-search-api"
    site_url = "https://developer.here.com"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize HERE backend.

        Args:
            config: Configuration dict with HERE_APP_ID and HERE_APP_CODE.
        """
        super().__init__(config)
        self._app_id = self._config.get("HERE_APP_ID")
        self._app_code = self._config.get("HERE_APP_CODE")

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

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the HERE API."""
        if not self._app_id or not self._app_code:
            return {"error": "HERE_APP_ID and HERE_APP_CODE must be configured"}

        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        base_url = "https://geocoder.api.here.com/6.2"
        url = f"{base_url}{endpoint}"

        request_params: Dict[str, Any] = {"app_id": self._app_id, "app_code": self._app_code}
        if params:
            request_params.update(params)

        try:
            response = requests.get(url, params=request_params, timeout=10)
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
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Validate an address using HERE Geocoding API."""
        search_text = self._build_address_string(
            address_line1,
            address_line2,
            address_line3,
            city,
            postal_code,
            state,
            country,
        )

        if not search_text:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Address query is empty"],
            }

        params = {"searchtext": search_text, "maxresults": 5}
        if country:
            params["country"] = country

        result = self._make_request("/geocode.json", params)

        if "error" in result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": [result["error"]],
            }

        response = result.get("Response", {})
        view = response.get("View", [])
        if not view:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["No address found"],
            }

        results = view[0].get("Result", [])
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

        match_quality = best_match.get("MatchQuality", {})
        relevance = match_quality.get("Relevance", 0.0) / 100.0
        confidence = relevance

        match_level = match_quality.get("MatchLevel", "")
        is_valid = (
            match_level in ("houseNumber", "street", "intersection")
            and confidence >= 0.7
        )

        suggestions = []
        if not is_valid and len(results) > 1:
            for result_item in results[1:5]:
                item_match_quality = result_item.get("MatchQuality", {})
                item_relevance = item_match_quality.get("Relevance", 0.0) / 100.0
                location = result_item.get("Location", {})
                address = location.get("Address", {})
                suggestions.append(
                    {
                        "formatted_address": address.get("Label", ""),
                        "confidence": item_relevance,
                    }
                )

        warnings = []
        if match_level not in ("houseNumber", "street"):
            warnings.append(f"Match level is {match_level}, not exact address")
        if confidence < 0.9:
            warnings.append("Low confidence match")

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
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
        """Geocode an address to coordinates using HERE."""
        search_text = self._build_address_string(
            address_line1,
            address_line2,
            address_line3,
            city,
            postal_code,
            state,
            country,
        )

        if not search_text:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["Address query is empty"],
            }

        params = {"searchtext": search_text, "maxresults": 1}
        if country:
            params["country"] = country

        result = self._make_request("/geocode.json", params)

        if "error" in result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        response = result.get("Response", {})
        view = response.get("View", [])
        if not view:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["No address found"],
            }

        results = view[0].get("Result", [])
        if not results:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["No address found"],
            }

        best_result = results[0]
        location = best_result.get("Location", {})
        display_position = location.get("DisplayPosition", {})
        match_quality = best_result.get("MatchQuality", {})

        match_level = match_quality.get("MatchLevel", "")
        accuracy_map = {
            "houseNumber": "ROOFTOP",
            "street": "STREET",
            "intersection": "STREET",
            "postalCode": "CITY",
            "district": "CITY",
            "city": "CITY",
            "state": "REGION",
            "country": "COUNTRY",
        }
        accuracy = accuracy_map.get(match_level, "UNKNOWN")

        relevance = match_quality.get("Relevance", 0.0) / 100.0

        address = location.get("Address", {})

        return {
            "latitude": display_position.get("Latitude"),
            "longitude": display_position.get("Longitude"),
            "accuracy": accuracy,
            "confidence": relevance,
            "formatted_address": address.get("Label", ""),
            "errors": [],
        }

    def reverse_geocode(
        self, latitude: float, longitude: float, **kwargs: Any
    ) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using HERE."""
        params = {
            "prox": f"{latitude},{longitude},250",
            "mode": "retrieveAddresses",
            "maxresults": 1,
        }
        if "language" in kwargs:
            params["language"] = kwargs["language"]

        result = self._make_request("/geocode.json", params)

        if "error" in result:
            return {
                "address_line1": None,
                "address_line2": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "confidence": 0.0,
                "errors": [result["error"]],
            }

        response = result.get("Response", {})
        view = response.get("View", [])
        if not view:
            return {
                "address_line1": None,
                "address_line2": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "confidence": 0.0,
                "errors": ["No address found"],
            }

        results = view[0].get("Result", [])
        if not results:
            return {
                "address_line1": None,
                "address_line2": None,
                "city": None,
                "postal_code": None,
                "state": None,
                "country": None,
                "formatted_address": None,
                "confidence": 0.0,
                "errors": ["No address found"],
            }

        best_result = results[0]
        normalized = self._extract_address_from_result(best_result)

        match_quality = best_result.get("MatchQuality", {})
        relevance = match_quality.get("Relevance", 0.0) / 100.0

        location = best_result.get("Location", {})
        address = location.get("Address", {})

        return {
            **normalized,
            "formatted_address": address.get("Label", ""),
            "confidence": relevance,
            "errors": [],
        }

    def _extract_address_from_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a HERE result."""
        location = result.get("Location", {})
        address = location.get("Address", {})

        address_line1 = ""
        street = address.get("Street", "")
        house_number = address.get("HouseNumber", "")
        if house_number and street:
            address_line1 = f"{house_number} {street}".strip()
        elif street:
            address_line1 = street

        city = address.get("City", "")
        postal_code = address.get("PostalCode", "")
        state = address.get("State", "")
        country = address.get("Country", "").upper()

        return {
            "address_line1": address_line1,
            "address_line2": "",
            "address_line3": "",
            "city": city,
            "postal_code": postal_code,
            "state": state,
            "country": country,
        }
