# routes/services.py

import csv
import math
import requests
from django.conf import settings

_FUEL_STATIONS = []
# Cache expires only on server restart — improves response time significantly
def _load_fuel_stations():
    global _FUEL_STATIONS
    if _FUEL_STATIONS:
        return _FUEL_STATIONS
    stations = []
    with open(settings.FUEL_PRICES_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stations.append({
                'state': row['state'],
                'city': row['city'],
                'lat': float(row['lat']),
                'lng': float(row['lng']),
                'price_per_gallon': float(row['price_per_gallon']),
            })
    _FUEL_STATIONS = stations
    return _FUEL_STATIONS


def haversine_miles(lat1, lng1, lat2, lng2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def geocode_city(city_name: str):
    url = 'https://nominatim.openstreetmap.org/search'
    params = {
        'q': f'{city_name}, USA',
        'format': 'json',
        'limit': 1,
        'countrycodes': 'us',
    }
    headers = {'User-Agent': 'FuelRouteAPI/1.0'}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f'Could not geocode location: {city_name}')
    return float(results[0]['lat']), float(results[0]['lon'])


def get_route_from_osrm(waypoints: list):
    coords = ';'.join(f'{lng},{lat}' for lat, lng in waypoints)
    url = f'{settings.OSRM_BASE_URL}/route/v1/driving/{coords}'
    params = {
        'overview': 'full',
        'geometries': 'geojson',
        'steps': 'false',
        'annotations': 'false',
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get('code') != 'Ok':
        raise ValueError(f"OSRM error: {data.get('message', 'Unknown error')}")
    return data


def find_optimal_fuel_stops(start_lat, start_lng, end_lat, end_lng):
    """
    Greedy algorithm:
    - Tank starts FULL (500 mile range)
    - At each stop, we FILL UP completely
    - Always pick cheapest station reachable within 500 miles
      that makes forward progress toward destination
    """
    MAX_RANGE = 500
    stations = _load_fuel_stations()

    chosen_stops = []
    current_lat, current_lng = start_lat, start_lng
    visited_ids = set()

    for _ in range(30):  # max 30 stops safety limit
        dist_to_dest = haversine_miles(current_lat, current_lng, end_lat, end_lng)

        # Can we reach destination directly? Done.
        if dist_to_dest <= MAX_RANGE:
            break

        # Find all stations within MAX_RANGE that make forward progress
        candidates = []
        for i, s in enumerate(stations):
            if i in visited_ids:
                continue
            d_from_here = haversine_miles(current_lat, current_lng, s['lat'], s['lng'])
            d_to_dest = haversine_miles(s['lat'], s['lng'], end_lat, end_lng)

            # Must be reachable AND closer to destination than we are now
            if d_from_here <= MAX_RANGE and d_to_dest < dist_to_dest:
                candidates.append({
                    'index': i,
                    'station': s,
                    'd_from_here': d_from_here,
                    'd_to_dest': d_to_dest,
                })

        if not candidates:
            # Fallback: just pick the reachable station closest to destination
            for i, s in enumerate(stations):
                if i in visited_ids:
                    continue
                d_from_here = haversine_miles(current_lat, current_lng, s['lat'], s['lng'])
                d_to_dest = haversine_miles(s['lat'], s['lng'], end_lat, end_lng)
                if d_from_here <= MAX_RANGE:
                    candidates.append({
                        'index': i,
                        'station': s,
                        'd_from_here': d_from_here,
                        'd_to_dest': d_to_dest,
                    })
            if not candidates:
                break
            # Pick closest to destination in fallback
            best = min(candidates, key=lambda x: x['d_to_dest'])
        else:
            # Pick CHEAPEST among forward candidates
            best = min(candidates, key=lambda x: x['station']['price_per_gallon'])

        s = best['station']
        chosen_stops.append({
            **s,
            'distance_from_prev_stop_miles': round(best['d_from_here'], 1),
        })
        visited_ids.add(best['index'])
        current_lat, current_lng = s['lat'], s['lng']

    return chosen_stops


def build_route_response(start: str, end: str):
    MPG = 10
    MAX_RANGE = 500

    # 1. Geocode
    start_lat, start_lng = geocode_city(start)
    end_lat, end_lng = geocode_city(end)

    # 2. Find fuel stops (pure Python, no API)
    fuel_stops = find_optimal_fuel_stops(start_lat, start_lng, end_lat, end_lng)

    # 3. Build waypoints for single OSRM call
    waypoints = [(start_lat, start_lng)]
    for s in fuel_stops:
        waypoints.append((s['lat'], s['lng']))
    waypoints.append((end_lat, end_lng))

    # 4. ONE OSRM API call
    osrm_data = get_route_from_osrm(waypoints)
    route = osrm_data['routes'][0]
    total_distance_meters = route['distance']
    total_duration_seconds = route['duration']
    geometry = route['geometry']

    total_miles = total_distance_meters / 1609.344
    total_gallons = total_miles / MPG

    # 5. Calculate fuel cost per leg
    all_points = (
        [(start_lat, start_lng, start, None)] +
        [(s['lat'], s['lng'], f"{s['city']}, {s['state']}", s['price_per_gallon'])
         for s in fuel_stops] +
        [(end_lat, end_lng, end, None)]
    )

    legs = []
    total_fuel_cost = 0.0

    for i in range(len(all_points) - 1):
        a = all_points[i]
        b = all_points[i + 1]
        leg_miles = haversine_miles(a[0], a[1], b[0], b[1])
        gallons = leg_miles / MPG

        # Use the price at the fueling point (point a if it's a stop, else first stop)
        if i < len(fuel_stops):
            price = fuel_stops[i]['price_per_gallon']
        else:
            price = fuel_stops[-1]['price_per_gallon'] if fuel_stops else 0.0

        cost = round(gallons * price, 2)
        total_fuel_cost += cost

        legs.append({
            'from': a[2],
            'to': b[2],
            'approx_miles': round(leg_miles, 1),
            'gallons': round(gallons, 2),
            'price_per_gallon': price,
            'leg_cost_usd': cost,
        })

    # 6. Fuel stops output
    stops_output = [{
        'city': s['city'],
        'state': s['state'],
        'lat': s['lat'],
        'lng': s['lng'],
        'price_per_gallon': s['price_per_gallon'],
        'distance_from_prev_stop_miles': s['distance_from_prev_stop_miles'],
    } for s in fuel_stops]

    return {
        'start': start,
        'end': end,
        'start_coords': {'lat': round(start_lat, 6), 'lng': round(start_lng, 6)},
        'end_coords': {'lat': round(end_lat, 6), 'lng': round(end_lng, 6)},
        'total_distance_miles': round(total_miles, 1),
        'total_duration_minutes': round(total_duration_seconds / 60, 1),
        'total_gallons_needed': round(total_gallons, 2),
        'total_fuel_cost_usd': round(total_fuel_cost, 2),
        'vehicle_range_miles': MAX_RANGE,
        'mpg': MPG,
        'number_of_fuel_stops': len(stops_output),
        'fuel_stops': stops_output,
        'leg_breakdown': legs,
        'route_geometry': geometry,
        'waypoints': [{'lat': lat, 'lng': lng} for lat, lng in waypoints],
        'osrm_api_calls_made': 1,
    }