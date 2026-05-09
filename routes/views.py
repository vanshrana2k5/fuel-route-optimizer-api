# routes/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import build_route_response


class RouteView(APIView):
    """
    POST /api/route/
    Body: { "start": "Dallas, TX", "end": "Chicago, IL" }
    """

    def post(self, request):
        start = request.data.get('start', '').strip()
        end = request.data.get('end', '').strip()

        if not start or not end:
            return Response(
                {'error': 'Both "start" and "end" fields are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = build_route_response(start, end)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Unexpected error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )