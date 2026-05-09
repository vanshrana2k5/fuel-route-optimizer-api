import csv
import os
import math
import json
import requests
from django.conf import settings

MPG = 10
MAX_RANGE_MILES = 500


# ── Load stations from cache ───────────────────────────────────────────────────
def load_fuel_stations():
    cache_path = os.path.join(settings.BASE_DIR, "stations_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    raise FileNotFoundError("stations_cache.json not found. Run: python build_cache.py")


# ── Geocode a place name ───────────────────────────────────────────────────────
def geocode(place: str):
    params = {
        "q":            place + ", USA",
        "format":       "json",
        "limit":        1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": "FuelRouteAPI/1.0"}
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params=params,
        headers=headers,
        timeout=10
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode '{place}'")
    return float(results[0]["lat"]), float(results[0]["lon"])


# ── Get route from OSRM (1 API call) ──────────────────────────────────────────
def get_route(start_coords, end_coords):
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start_coords[1]},{start_coords[0]};"
        f"{end_coords[1]},{end_coords[0]}"
        f"?overview=full&geometries=geojson&steps=false"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    route = resp.json()["routes"][0]
    return {
        "distance_miles": round(route["distance"] / 1609.344, 2),
        "geometry":        route["geometry"],
        "coords":          route["geometry"]["coordinates"],
    }


# ── Haversine distance in miles ────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ── Sample points along route every N miles ────────────────────────────────────
def sample_route_points(coords, interval_miles=40):
    if not coords:
        return []
    samples = [(coords[0][1], coords[0][0])]
    accumulated = 0.0
    for i in range(1, len(coords)):
        prev_lon, prev_lat = coords[i-1]
        curr_lon, curr_lat = coords[i]
        accumulated += haversine(prev_lat, prev_lon, curr_lat, curr_lon)
        if accumulated >= interval_miles:
            samples.append((curr_lat, curr_lon))
            accumulated = 0.0
    last = coords[-1]
    if samples[-1] != (last[1], last[0]):
        samples.append((last[1], last[0]))
    return samples


# ── Find cheapest station within max_miles of a point ─────────────────────────
def find_cheapest_station_near(point_lat, point_lon, stations, max_miles=75):
    nearby = []
    for s in stations:
        if s["lat"] is None or s["lon"] is None:
            continue
        dist = haversine(point_lat, point_lon, s["lat"], s["lon"])
        if dist <= max_miles:
            nearby.append((s["price"], dist, s))
    if not nearby:
        return None
    nearby.sort(key=lambda x: x[0])  # cheapest first
    return nearby[0][2]


# ── Plan fuel stops along route ────────────────────────────────────────────────
def plan_fuel_stops(route_data, stations):
    total_miles = route_data["distance_miles"]
    route_points = sample_route_points(route_data["coords"], interval_miles=40)

    fuel_stops = []
    seen = set()
    miles_since_fill = 0

    for i, (lat, lon) in enumerate(route_points):
        # Accumulate miles since last fuel stop
        if i > 0:
            prev_lat, prev_lon = route_points[i-1]
            miles_since_fill += haversine(prev_lat, prev_lon, lat, lon)

        # Fuel up when within 100 miles of running out
        if miles_since_fill >= (MAX_RANGE_MILES - 100):
            station = find_cheapest_station_near(lat, lon, stations)
            if station:
                key = (station["name"], station["city"])
                if key not in seen:
                    seen.add(key)
                    fuel_stops.append(station)
                    miles_since_fill = 0

    # Calculate total fuel cost
    gallons_needed = total_miles / MPG
    if fuel_stops:
        avg_price = sum(s["price"] for s in fuel_stops) / len(fuel_stops)
    else:
        # No stops found, use cheapest available station price
        valid = [s["price"] for s in stations if s["lat"] is not None]
        avg_price = min(valid) if valid else 0

    total_cost = round(gallons_needed * avg_price, 2)
    return fuel_stops, total_cost, round(gallons_needed, 2)


# ── In-memory cache (loaded once at startup) ───────────────────────────────────
_CACHED_STATIONS = None

def get_cached_stations():
    global _CACHED_STATIONS
    if _CACHED_STATIONS is None:
        _CACHED_STATIONS = load_fuel_stations()
    return _CACHED_STATIONS