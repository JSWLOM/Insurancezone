import math
from config import get_settings

settings = get_settings()


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance in metres between two GPS points
    using the Haversine formula.

    Args:
        lat1, lng1: First coordinate (e.g. employee GPS)
        lat2, lng2: Second coordinate (e.g. office location)

    Returns:
        Distance in metres (float)
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


def is_inside_geofence(lat: float, lng: float) -> tuple[bool, float]:
    """
    Check whether a GPS coordinate is within the office geo-fence.

    Returns:
        (is_inside: bool, distance_metres: float)
    """
    distance = haversine_distance(
        lat, lng,
        settings.office_lat,
        settings.office_lng,
    )
    return distance <= settings.office_radius_meters, round(distance, 1)


def office_coords() -> dict:
    return {
        "lat": settings.office_lat,
        "lng": settings.office_lng,
        "radius_meters": settings.office_radius_meters,
    }