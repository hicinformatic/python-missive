"""Photon (Komoot) address verification backend."""

from __future__ import annotations

from typing import Any, Dict, Optional, cast

from .base import BaseAddressBackend


class PhotonAddressBackend(BaseAddressBackend):
    """Photon (Komoot) Geocoding API backend for address verification.

    Completely free, no API key required. Fast geocoding based on OpenStreetMap data.
    Provided by Komoot.
    """

    name = "photon"
    display_name = "Photon (Komoot)"
    config_keys = ["PHOTON_BASE_URL"]
    required_packages = ["requests"]
    documentation_url = "https://photon.komoot.io/"
    site_url = "https://photon.komoot.io"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Photon backend.

        Args:
            config: Optional configuration dict with:
                - PHOTON_BASE_URL: Custom Photon server URL (default: official)
        """
        super().__init__(config)
        self._base_url = self._config.get("PHOTON_BASE_URL", "https://photon.komoot.io")

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
        """Make a request to the Photon API."""
        try:
            import requests
        except ImportError:
            return {"error": "requests package not installed"}

        url = f"{self._base_url}{endpoint}"

        request_params = {}
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

    def validate_address(  # noqa: C901
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
        """Validate an address using Photon."""
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
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["Address query is empty"],
            }

        params = {"q": query_string, "limit": 5}
        if country:
            params["osm_tag"] = f"place:country={country}"

        result = self._make_request("/api", params)

        if "error" in result:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "is_valid": False,
                "normalized_address": {},
                "confidence": 0.0,
                "suggestions": [],
                "warnings": [],
                "errors": ["No address found"],
            }

        best_match = features[0]
        normalized = self._extract_address_from_feature(best_match)

        # Extract coordinates from geometry (GeoJSON format: [longitude, latitude])
        coordinates = best_match.get("geometry", {}).get("coordinates", [])
        if len(coordinates) >= 2:
            normalized["longitude"] = float(coordinates[0])
            normalized["latitude"] = float(coordinates[1])

        properties = best_match.get("properties", {})

        # Calculate confidence based on address completeness since Photon doesn't return importance
        # Score: 1.0 if we have all key fields, lower if missing
        confidence_score = 0.0
        if properties.get("housenumber") and properties.get("street"):
            confidence_score = 0.9  # Complete address with house number and street
        elif properties.get("street"):
            confidence_score = 0.7  # Street without house number
        elif properties.get("city") or properties.get("postcode"):
            confidence_score = 0.5  # Only city or postal code

        # Use importance if available (fallback for some Photon instances)
        importance = properties.get("importance")
        if importance is not None:
            confidence_score = min(float(importance) * 2.0, 1.0)

        confidence = confidence_score

        # Add confidence to normalized_address
        normalized["confidence"] = confidence

        is_valid = confidence >= 0.5

        suggestions = []
        if not is_valid and len(features) > 1:
            for feature in features[1:5]:
                feat_props = feature.get("properties", {})
                feat_importance = feat_props.get("importance", 0.0)
                suggestion_data = {
                    "formatted_address": feat_props.get("name", ""),
                    "confidence": min(feat_importance * 2.0, 1.0),
                }
                # Add coordinates to suggestions
                feat_coords = feature.get("geometry", {}).get("coordinates", [])
                if len(feat_coords) >= 2:
                    suggestion_data["longitude"] = float(feat_coords[0])
                    suggestion_data["latitude"] = float(feat_coords[1])
                suggestions.append(suggestion_data)

        warnings = []
        if importance is not None and importance < 0.5:
            warnings.append("Low importance match")
        if confidence < 0.7:
            warnings.append("Low confidence match")

        # Extract OSM reference from best match
        best_properties = best_match.get("properties", {})
        osm_id = best_properties.get("osm_id")
        osm_type = best_properties.get("osm_type")
        address_reference = None
        if osm_id is not None and osm_type:
            address_reference = f"{osm_type}:{osm_id}"

        return {
            "is_valid": is_valid,
            "normalized_address": normalized,
            "confidence": confidence,
            "suggestions": suggestions,
            "warnings": warnings,
            "errors": [],
            "address_reference": address_reference or normalized.get("address_reference"),
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
        """Geocode an address to coordinates using Photon."""
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
            params["osm_tag"] = f"place:country={country}"

        result = self._make_request("/api", params)

        if "error" in result:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": [result["error"]],
            }

        features = result.get("features", [])
        if not features:
            return {
                "latitude": None,
                "longitude": None,
                "accuracy": None,
                "confidence": 0.0,
                "formatted_address": None,
                "errors": ["No address found"],
            }

        feature = features[0]
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        properties = feature.get("properties", {})

        osm_type = properties.get("osm_type", "")
        osm_key = properties.get("osm_key", "")
        accuracy_map = {
            "node": "ROOFTOP" if osm_key == "place" else "STREET",
            "way": "STREET",
            "relation": "CITY",
        }
        accuracy = accuracy_map.get(osm_type, "UNKNOWN")

        importance = properties.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        # Extract OSM reference
        osm_id = properties.get("osm_id")
        osm_type = properties.get("osm_type")
        address_reference = None
        if osm_id is not None and osm_type:
            address_reference = f"{osm_type}:{osm_id}"

        return {
            "latitude": coordinates[1] if len(coordinates) >= 2 else None,
            "longitude": coordinates[0] if len(coordinates) >= 1 else None,
            "accuracy": accuracy,
            "confidence": confidence,
            "formatted_address": properties.get("name", ""),
            "address_reference": address_reference,
            "errors": [],
        }

    def reverse_geocode(self, latitude: float, longitude: float, **kwargs: Any) -> Dict[str, Any]:
        """Reverse geocode coordinates to an address using Photon."""
        params = {"lat": str(latitude), "lon": str(longitude), "limit": 1}
        if "language" in kwargs:
            params["lang"] = kwargs["language"]

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

        features = result.get("features", [])
        if not features:
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

        feature = features[0]
        normalized = self._extract_address_from_feature(feature)

        properties = feature.get("properties", {})
        importance = properties.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        return {
            **normalized,
            "formatted_address": properties.get("name", ""),
            "confidence": confidence,
            "address_reference": normalized.get("address_reference"),
            "errors": [],
        }

    def get_address_by_reference(self, address_reference: str, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve an address by its OSM reference (osm_type:osm_id).

        Note: Photon API does not directly support lookup by OSM ID.
        This implementation attempts to use the reference but may not work
        for all cases. Consider using Nominatim backend for reliable ID-based lookups.
        """
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

        if ":" not in address_reference:
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
                "errors": ["Invalid OSM reference format. Expected 'osm_type:osm_id'"],
            }

        parts = address_reference.split(":", 1)
        if len(parts) != 2:
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
                "errors": ["Invalid OSM reference format"],
            }

        osm_type, osm_id_str = parts
        try:
            osm_id = int(osm_id_str)
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
                "errors": ["Invalid OSM ID format"],
            }

        params = {"osm_ids": f"{osm_type},{osm_id}", "limit": 1}
        if "language" in kwargs:
            params["lang"] = kwargs["language"]

        result = self._make_request("/api", params)

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

        features = result.get("features", [])
        if not features:
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
                "errors": ["No address found for this OSM reference"],
            }

        feature = features[0]
        normalized = self._extract_address_from_feature(feature)

        coordinates = feature.get("geometry", {}).get("coordinates", [])
        properties = feature.get("properties", {})
        importance = properties.get("importance", 0.0)
        confidence = min(importance * 2.0, 1.0)

        return {
            **normalized,
            "formatted_address": properties.get("name", ""),
            "latitude": coordinates[1] if len(coordinates) >= 2 else None,
            "longitude": coordinates[0] if len(coordinates) >= 1 else None,
            "confidence": confidence,
            "address_reference": address_reference,
            "errors": [],
        }

    def _extract_address_from_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address components from a Photon feature."""
        properties = feature.get("properties", {})

        address_line1 = ""
        house_number = properties.get("housenumber", "")
        street = properties.get("street", "")
        if house_number and street:
            address_line1 = f"{house_number} {street}".strip()
        elif street:
            address_line1 = street

        city = properties.get("city") or properties.get("town") or properties.get("village") or ""
        postal_code = properties.get("postcode", "")
        state = properties.get("state", "")
        country = properties.get("countrycode", "").upper()

        # Extract OSM reference (osm_id + osm_type for reverse lookup)
        osm_id = properties.get("osm_id")
        osm_type = properties.get("osm_type")
        address_reference = None
        if osm_id is not None and osm_type:
            # Format: "osm_type:osm_id" for reverse lookup
            address_reference = f"{osm_type}:{osm_id}"

        return {
            "address_line1": address_line1,
            "address_line2": "",
            "address_line3": "",
            "city": city,
            "postal_code": postal_code,
            "state": state,
            "country": country,
            "address_reference": address_reference,
        }
