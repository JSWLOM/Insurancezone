import math
from config import get_settings

settings = get_settings()


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Great-circle distance in metres between two GPS coordinates.
    Identical formula used in the JS frontend (haversineJS) — they must stay in sync.
    """
    R = 6_371_000  # Earth radius in metres

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ── Single-office (legacy) ─────────────────────────────────────
# Reads coordinates from .env via settings.
# Kept for backward compatibility but NO LONGER called by punch-in/out.
# Those now use is_inside_geofence_for_office() below.

def is_inside_geofence(lat: float, lng: float) -> tuple[bool, float]:
    distance = haversine_distance(lat, lng, settings.office_lat, settings.office_lng)
    return distance <= settings.office_radius_meters, round(distance, 1)


def office_coords() -> dict:
    """Legacy single-office coords from .env — fallback only."""
    return {
        "lat":           settings.office_lat,
        "lng":           settings.office_lng,
        "radius_meters": settings.office_radius_meters,
    }


# ── Multi-office ───────────────────────────────────────────────
# office dict must have: lat (float), lng (float), radius_meters (float)
# This is the MongoDB office document fetched by _get_employee_office().

def is_inside_geofence_for_office(
    lat: float,
    lng: float,
    office: dict,
) -> tuple[bool, float]:
    """
    Check whether GPS coordinates fall within a specific office's geo-fence.

    Args:
        lat, lng  — employee's current GPS position
        office    — office document from MongoDB with lat, lng, radius_meters

    Returns:
        (is_inside: bool, distance_metres: float)
    """
    distance = haversine_distance(
        lat, lng,
        office["lat"],
        office["lng"],
    )
    radius = office.get("radius_meters", 200)
    return distance <= radius, round(distance, 1)