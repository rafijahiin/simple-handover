from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import CanWriteOrgRecord
from partners.models import Partner

from .models import ApprovalStatus, PrescriptionRecord
from .serializers import PrescriptionRecordSerializer


class PrescriptionRecordViewSet(viewsets.ModelViewSet):
    """
    /api/pharmacy/prescriptions/

    Reads are org-scoped (a user without cross-org visibility sees only their
    partner's records). Writes are gated by CanWriteOrgRecord (the view-only
    `focal` and survey-only `ciprb_baseline` roles cannot write) and the
    `partner` is PINNED to the writer's OWN organisation — a user can never POST
    a prescription under another partner, and can never self-approve:
    `partner`, `approval_status` and `prescribed_by` are server-set, and the
    only way to change the status is the gated approve/reject action below.
    """
    serializer_class = PrescriptionRecordSerializer
    permission_classes = [CanWriteOrgRecord]
    queryset = (
        PrescriptionRecord.objects
        .select_related('partner', 'center', 'prescribed_by')
        .all()
    )

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not getattr(user, 'can_read_other_orgs', False):
            qs = qs.filter(partner__code=user.organisation)
        drug    = self.request.query_params.get('drug')
        date    = self.request.query_params.get('date')
        partner = self.request.query_params.get('partner')
        if drug:
            qs = qs.filter(drug=drug)
        if date:
            qs = qs.filter(date=date)
        if partner and getattr(user, 'can_read_other_orgs', False):
            qs = qs.filter(partner__code=partner)
        return qs.order_by('-date', '-created_at')

    def _own_partner(self) -> Partner:
        partner = Partner.objects.filter(code=self.request.user.organisation).first()
        if partner is None:
            raise ValidationError({'partner': (
                f'No partner record for your organisation '
                f'({self.request.user.organisation}); prescriptions are PHD/Bandhu data.')})
        return partner

    def perform_create(self, serializer):
        # Pin partner to the writer's org (no cross-org forgery); prescribed_by
        # to the user; approval_status falls to the model default (PENDING).
        serializer.save(prescribed_by=self.request.user, partner=self._own_partner())

    def perform_update(self, serializer):
        # An update can never move a record to another partner or self-approve
        # (those fields are read-only on the serializer); re-pin partner
        # defensively for org-bound writers.
        user = self.request.user
        if getattr(user, 'can_read_other_orgs', False):
            serializer.save()
        else:
            serializer.save(partner=self._own_partner())

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._set_status(request, ApprovalStatus.APPROVED)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._set_status(request, ApprovalStatus.REJECTED)

    def _set_status(self, request, new_status):
        user = request.user
        if not getattr(user, 'can_approve_submissions', False):
            return Response({'detail': 'You cannot approve prescriptions.'},
                            status=status.HTTP_403_FORBIDDEN)
        obj = self.get_object()   # already org-scoped by get_queryset
        if not (getattr(user, 'can_read_other_orgs', False)
                or obj.partner.code == user.organisation):
            return Response({'detail': 'Cross-org approval denied.'},
                            status=status.HTTP_403_FORBIDDEN)
        obj.approval_status = new_status
        obj.save()
        return Response({'status': obj.approval_status})
