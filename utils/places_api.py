"""
Google Maps Platform wrappers: reverse-geocoding + nearby-place search.

Uses the official `googlemaps` Python client which calls the
classic Places API (Nearby Search) under the hood.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import googlemaps


# Mapping from a category label shown in the UI to a Google Places "type".
# See https://developers.google.com/maps/documentation/places/web-service/supported_types
CATEGORY_TYPES: Dict[str, str] = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "tourist_attraction": "tourist_attraction",
}

# Human-readable Korean labels for each category.
CATEGORY_LABELS_KO: Dict[str, str] = {
    "restaurant": "🍽️ 주변 맛집",
    "cafe": "☕ 카페 / 디저트",
    "tourist_attraction": "🗺️ 관광 명소",
}

# Pin colors for folium markers per category.
CATEGORY_COLORS: Dict[str, str] = {
    "restaurant": "red",
    "cafe": "orange",
    "tourist_attraction": "blue",
}


@dataclass
class Place:
    """Lightweight representation of a Google Place result."""

    place_id: str
    name: str
    category: str
    latitude: float
    longitude: float
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    address: Optional[str] = None
    photo_reference: Optional[str] = None
    types: List[str] = field(default_factory=list)
    open_now: Optional[bool] = None

    @property
    def google_maps_url(self) -> str:
        """Direct Google Maps URL keyed by place_id."""
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query={self.latitude},{self.longitude}"
            f"&query_place_id={self.place_id}"
        )

    def photo_url(self, api_key: str, max_width: int = 400) -> Optional[str]:
        """Build a Google Place Photo URL for the first thumbnail."""
        if not self.photo_reference:
            return None
        return (
            "https://maps.googleapis.com/maps/api/place/photo"
            f"?maxwidth={max_width}"
            f"&photo_reference={self.photo_reference}"
            f"&key={api_key}"
        )


class PlacesClient:
    """Thin wrapper around googlemaps.Client for our two use cases."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Google Maps API key is required.")
        self.api_key = api_key
        self.gmaps = googlemaps.Client(key=api_key)

    # ------------------------------------------------------------------
    # Reverse geocoding
    # ------------------------------------------------------------------
    def reverse_geocode(
        self, latitude: float, longitude: float, language: str = "ko"
    ) -> Optional[str]:
        """Return a formatted address for a coordinate, or None."""
        try:
            results = self.gmaps.reverse_geocode(
                (latitude, longitude), language=language
            )
        except Exception:
            return None
        if not results:
            return None
        return results[0].get("formatted_address")

    # ------------------------------------------------------------------
    # Nearby search
    # ------------------------------------------------------------------
    def nearby(
        self,
        latitude: float,
        longitude: float,
        category: str,
        radius_m: int = 1000,
        max_results: int = 8,
        language: str = "ko",
    ) -> List[Place]:
        """
        Search Google Places within `radius_m` meters of the coordinate.

        `category` must be a key from CATEGORY_TYPES.
        Returns at most `max_results` places, sorted by Google's
        prominence ranking (which roughly correlates with popularity).
        """
        place_type = CATEGORY_TYPES.get(category)
        if not place_type:
            raise ValueError(f"Unknown category: {category}")

        try:
            resp = self.gmaps.places_nearby(
                location=(latitude, longitude),
                radius=radius_m,
                type=place_type,
                language=language,
            )
        except Exception as e:
            raise RuntimeError(f"Places API request failed: {e}") from e

        places: List[Place] = []
        for item in resp.get("results", [])[:max_results]:
            loc = item.get("geometry", {}).get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")
            if lat is None or lng is None:
                continue

            photos = item.get("photos") or []
            photo_ref = photos[0].get("photo_reference") if photos else None

            opening = item.get("opening_hours") or {}
            open_now = opening.get("open_now")

            places.append(
                Place(
                    place_id=item.get("place_id", ""),
                    name=item.get("name", "Unknown"),
                    category=category,
                    latitude=float(lat),
                    longitude=float(lng),
                    rating=item.get("rating"),
                    user_ratings_total=item.get("user_ratings_total"),
                    address=item.get("vicinity") or item.get("formatted_address"),
                    photo_reference=photo_ref,
                    types=item.get("types", []),
                    open_now=open_now,
                )
            )

        return places
