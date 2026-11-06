from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from .models import Partner
from .serializers import PartnerSerializer


class PartnerViewSet(ReadOnlyModelViewSet):
    """Read-only — the 3 partner rows are seeded via migration and not
    mutated through the API. List + retrieve only."""
    queryset = Partner.objects.filter(is_active=True).order_by('code')
    serializer_class = PartnerSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'code'
