import json
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .services import geocode, get_route, get_cached_stations, plan_fuel_stops


def build_map_url(start_coords, end_coords):
    from_lat, from_lon = start_coords
    to_lat, to_lon = end_coords
    return (
        f"https://www.openstreetmap.org/directions?"
        f"engine=fossgis_osrm_car&"
        f"route={from_lat},{from_lon};{to_lat},{to_lon}"
    )


@method_decorator(csrf_exempt, name='dispatch')
class RouteView(View):

    def get(self, request):
        start = request.GET.get("start", "").strip()
        end   = request.GET.get("end", "").strip()
        return self._handle(start, end)

    def post(self, request):
        try:
            body  = json.loads(request.body)
            start = body.get("start", "").strip()
            end   = body.get("end", "").strip()
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)
        return self._handle(start, end)

    def _handle(self, start, end):
        if not start or not end:
            return JsonResponse({"error": "Provide both 'start' and 'end'."}, status=400)

        try:
            start_coords = geocode(start)
            end_coords   = geocode(end)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"Geocoding failed: {str(e)}"}, status=502)

        try:
            route_data = get_route(start_coords, end_coords)
        except Exception as e:
            return JsonResponse({"error": f"Routing failed: {str(e)}"}, status=502)

        stations = get_cached_stations()
        fuel_stops, total_cost, gallons = plan_fuel_stops(route_data, stations)
        map_url = build_map_url(start_coords, end_coords)

        return JsonResponse({
            "start":           start,
            "end":             end,
            "total_miles":     route_data["distance_miles"],
            "gallons_needed":  gallons,
            "total_fuel_cost": f"${total_cost}",
            "map_url":         map_url,
            "fuel_stops": [
                {
                    "name":  s["name"],
                    "city":  s["city"],
                    "state": s["state"],
                    "price": f"${s['price']:.3f}",
                    "lat":   s["lat"],
                    "lon":   s["lon"],
                }
                for s in fuel_stops
            ],
            "route_geometry": route_data["geometry"],
        })