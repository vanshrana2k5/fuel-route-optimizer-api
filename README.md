# ⛽ Fuel Route Optimizer API

A Django REST API that calculates the **most cost-effective route** for a road trip across the USA — finding the cheapest fuel stops along the way based on real gas prices.

---

## 📌 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [How the Algorithm Works](#how-the-algorithm-works)
- [Example Response](#example-response)
- [Requirements Checklist](#requirements-checklist)

---

## Overview

Given a **start** and **end** location anywhere in the USA, this API:

1. Finds the optimal driving route
2. Identifies where to stop for fuel along the way (based on lowest price)
3. Assumes the vehicle has a **500-mile maximum range** and gets **10 MPG**
4. Returns the **total fuel cost** for the entire trip
5. Returns a **GeoJSON map** of the route for rendering

The routing is powered by **OSRM** (Open Source Routing Machine) — a free, open-source routing engine with no API key required. The entire route including all fuel stops is calculated in **a single API call**.

---

## Features

- 🗺️ **Route mapping** — Full GeoJSON geometry for rendering on any map library (Leaflet, Mapbox, Google Maps)
- ⛽ **Optimal fuel stops** — Cheapest stations selected using a greedy algorithm
- 💰 **Cost breakdown** — Total fuel cost + per-leg breakdown
- 🚗 **Range-aware** — Respects 500-mile tank limit, adds stops automatically
- ⚡ **Fast responses** — Fuel price data cached in memory at startup, only 1 routing API call made
- 🔗 **Map URL** — Direct OpenStreetMap link to visualise the route in browser

---

## Tech Stack

| Component | Technology | Notes |
|---|---|---|
| Framework | Django 5.x + Django REST Framework | Latest stable Django |
| Routing API | [OSRM](http://router.project-osrm.org) | Free, no API key, 1 call per request |
| Geocoding | [Nominatim](https://nominatim.openstreetmap.org) (OpenStreetMap) | Free, no API key |
| Fuel Data | CSV file (42 US cities) | Loaded once into memory at startup |
| Algorithm | Greedy cheapest-first selection | O(n) per leg, very fast |
| Language | Python 3.10+ | |

---

## Project Structure

```
fuel_route_api/
│
├── config/                     # Django project configuration
│   ├── settings.py             # App settings, OSRM URL, CSV path
│   ├── urls.py                 # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
│
├── routes/                     # Main application
│   ├── services.py             # Core logic: geocoding, routing, algorithm
│   ├── views.py                # API view (POST /api/route/)
│   ├── urls.py                 # Route-level URL config
│   ├── models.py
│   └── apps.py
│
├── fuel_prices.csv             # Fuel price data for 42 US cities
├── manage.py
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- pip
- Git

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/your-username/fuel_route_api.git
cd fuel_route_api
```

**2. Create and activate a virtual environment**
```bash
# Windows
python -m venv venv
venv\Scripts\Activate.ps1

# Mac / Linux
python -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Run database migrations**
```bash
python manage.py migrate
```

**5. Start the development server**
```bash
python manage.py runserver
```

The API is now live at `http://127.0.0.1:8000`

---

## API Reference

### `POST /api/route/`

Calculate the optimal fuel route between two US locations.

#### Request

| Field | Type | Required | Description |
|---|---|---|---|
| `start` | string | ✅ | Starting location (US city) |
| `end` | string | ✅ | Destination location (US city) |

**Example Request (cURL)**
```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Los Angeles, CA", "end": "New York City, NY"}'
```

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `start` | string | Start location as provided |
| `end` | string | End location as provided |
| `start_coords` | object | `{lat, lng}` of start |
| `end_coords` | object | `{lat, lng}` of end |
| `total_distance_miles` | float | Total driving distance |
| `total_duration_minutes` | float | Estimated drive time in minutes |
| `total_duration_hours` | float | Estimated drive time in hours |
| `mpg` | int | Miles per gallon assumed (10) |
| `vehicle_range_miles` | int | Max range on full tank (500) |
| `total_gallons_needed` | float | Total gallons for the trip |
| `total_fuel_cost_usd` | float | **Total cost in USD** |
| `number_of_fuel_stops` | int | How many stops needed |
| `fuel_stops` | array | Ordered list of fuel stops |
| `leg_breakdown` | array | Cost breakdown per leg |
| `route_geometry` | object | GeoJSON LineString for map rendering |
| `waypoints` | array | All lat/lng points including stops |
| `map_url` | string | OpenStreetMap URL to view route |
| `routing_api_calls_made` | int | Always `1` ✅ |

#### Fuel Stop Object

```json
{
    "city": "Phoenix",
    "state": "Arizona",
    "lat": 33.4484,
    "lng": -112.074,
    "price_per_gallon": 3.28,
    "distance_from_prev_stop_miles": 356.8
}
```

#### Leg Breakdown Object

```json
{
    "from": "Los Angeles, CA",
    "to": "Phoenix, Arizona",
    "approx_miles": 356.8,
    "gallons": 35.68,
    "price_per_gallon": 3.28,
    "leg_cost_usd": 116.94
}
```

#### Error Responses

| Status | Meaning |
|---|---|
| `400` | Missing fields or unrecognised location |
| `500` | Routing API unavailable or server error |

---

## How the Algorithm Works

```
START (full tank, 500 mile range)
  │
  ▼
Can we reach DESTINATION within 500 miles?
  │
  ├── YES → Done. No fuel stop needed.
  │
  └── NO  → Find all stations within 500 miles
              that bring us CLOSER to destination
                │
                ▼
             Pick the CHEAPEST one
                │
                ▼
             Drive there. Fill up. Repeat.
```

### Key Design Decisions

- **One OSRM call** — All waypoints (start + all fuel stops + end) are sent in a single request. OSRM handles multi-stop routing natively.
- **Memory caching** — The CSV is loaded into memory once at server startup. No file reads per request.
- **Greedy approach** — At each position, we look ahead up to 500 miles and pick the cheapest reachable station. Fast O(n) per iteration.
- **Forward progress filter** — Candidate stations must be closer to the destination than the current position to avoid backtracking.

---

## Example Response

**Request:**
```json
{
    "start": "Los Angeles, CA",
    "end": "New York City, NY"
}
```

**Response:**
```json
{
    "start": "Los Angeles, CA",
    "end": "New York City, NY",
    "start_coords": { "lat": 34.053691, "lng": -118.242766 },
    "end_coords":   { "lat": 40.712728, "lng": -74.006015 },
    "total_distance_miles": 2789.4,
    "total_duration_minutes": 2401.0,
    "total_duration_hours": 40.0,
    "mpg": 10,
    "vehicle_range_miles": 500,
    "total_gallons_needed": 278.94,
    "total_fuel_cost_usd": 987.45,
    "number_of_fuel_stops": 5,
    "fuel_stops": [
        {
            "city": "Phoenix",
            "state": "Arizona",
            "lat": 33.4484,
            "lng": -112.074,
            "price_per_gallon": 3.28,
            "distance_from_prev_stop_miles": 356.8
        },
        {
            "city": "Albuquerque",
            "state": "New Mexico",
            "lat": 35.0844,
            "lng": -106.6504,
            "price_per_gallon": 3.32,
            "distance_from_prev_stop_miles": 421.5
        }
    ],
    "leg_breakdown": [
        {
            "from": "Los Angeles, CA",
            "to": "Phoenix, Arizona",
            "approx_miles": 356.8,
            "gallons": 35.68,
            "price_per_gallon": 3.28,
            "leg_cost_usd": 116.94
        }
    ],
    "route_geometry": {
        "type": "LineString",
        "coordinates": [[-118.2423, 34.0534], "...hundreds of coordinate points..."]
    },
    "map_url": "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=...",
    "routing_api": "OSRM (router.project-osrm.org)",
    "routing_api_calls_made": 1
}
```

---

## Requirements Checklist

| Requirement | Status | Detail |
|---|---|---|
| Takes start & end USA location as input | ✅ | `POST /api/route/` with `start` and `end` fields |
| Returns map of the route | ✅ | GeoJSON `route_geometry` + `map_url` for OpenStreetMap |
| Optimal (cheapest) fuel stop locations | ✅ | Greedy cheapest-first algorithm |
| 500-mile maximum vehicle range | ✅ | Hard limit enforced in algorithm |
| Total fuel cost at 10 MPG | ✅ | `total_fuel_cost_usd` + full `leg_breakdown` |
| Uses provided fuel prices file | ✅ | `fuel_prices.csv` loaded at startup |
| Built in latest stable Django | ✅ | Django 5.x |
| API returns results quickly | ✅ | CSV cached in memory, O(n) algorithm |
| Minimal routing API calls (ideally 1) | ✅ | **Exactly 1 OSRM call** per request |

---

## Author

Built as part of a backend engineering assessment.