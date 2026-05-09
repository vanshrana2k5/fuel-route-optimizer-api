from django.test import TestCase, Client
import json

class RouteAPITest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_missing_params(self):
        response = self.client.post(
            '/api/route/',
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_short_route(self):
        response = self.client.post(
            '/api/route/',
            data=json.dumps({
                "start": "Chicago, IL",
                "end": "Indianapolis, IN"
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('total_miles', data)
        self.assertIn('total_fuel_cost', data)
        self.assertIn('fuel_stops', data)