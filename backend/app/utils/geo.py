"""Geographic helpers. Only coarse, user-provided city coordinates are used."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088

# Distance bands -> similarity score. Ordered from closest to furthest.
DISTANCE_BANDS: list[tuple[float, float]] = [
    (5.0, 1.0),
    (20.0, 0.8),
    (50.0, 0.5),
    (200.0, 0.2),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def distance_similarity(distance_km: float | None) -> float:
    """Map a distance to a 0-1 proximity score using the configured bands."""
    if distance_km is None:
        return 0.0
    for limit, score in DISTANCE_BANDS:
        if distance_km < limit:
            return score
    return 0.0


def location_similarity(
    lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None
) -> tuple[float, float | None]:
    """Return (similarity, distance_km). Missing coordinates score a neutral 0."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0, None
    distance = haversine_km(lat1, lon1, lat2, lon2)  # type: ignore[arg-type]
    return distance_similarity(distance), distance


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Cheap pre-filter box (min_lat, max_lat, min_lon, max_lon) for SQL."""
    lat_delta = radius_km / 111.0
    # Guard against the poles where the longitude degree collapses to zero.
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_km / (111.0 * cos_lat)
    return (
        max(lat - lat_delta, -90.0),
        min(lat + lat_delta, 90.0),
        max(lon - lon_delta, -180.0),
        min(lon + lon_delta, 180.0),
    )
