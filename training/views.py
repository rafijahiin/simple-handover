from io import BytesIO

from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsSupervisorOrManager, OrgFilterMixin
from .models import TrainingSession
from .serializers import (
    TrainingAttendanceSerializer,
    TrainingSessionSerializer,
    TrainingSessionWriteSerializer,
)


class TrainingSessionViewSet(OrgFilterMixin, ModelViewSet):
    queryset = TrainingSession.objects.prefetch_related('attendances').all()
    permission_classes = [IsSupervisorOrManager]
    org_field = 'partner'

    def get_queryset(self):
        qs = super().get_queryset()
        partner = self.request.query_params.get('partner')
        if partner and self.request.user.can_see_all_orgs:
            qs = qs.filter(partner=partner)
        return qs

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return TrainingSessionWriteSerializer
        return TrainingSessionSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        total_sessions = qs.count()
        total_attended = sum(s.actual_participants for s in qs)
        return Response({
            'total_sessions': total_sessions,
            'total_participants_attended': total_attended,
        })

    @action(detail=True, methods=['post'])
    def add_attendance(self, request, pk=None):
        session = self.get_object()
        serializer = TrainingAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(session=session)
        return Response(serializer.data, status=201)

    @action(detail=True, methods=['get'])
    def attendance(self, request, pk=None):
        session = self.get_object()
        qs = session.attendances.all()
        serializer = TrainingAttendanceSerializer(qs, many=True)
        return Response({'count': qs.count(), 'results': serializer.data})


class TrainingSummaryPDFView(APIView):
    """
    GET /api/training/summary-pdf/
    Downloads a PDF summary table of all training sessions visible to this user.
    """
    permission_classes = [IsSupervisorOrManager]

    def get(self, request):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        qs = TrainingSession.objects.prefetch_related('attendances').order_by('-date')
        if not request.user.can_see_all_orgs:
            qs = qs.filter(partner=request.user.organisation)

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph('Training Session Summary', styles['Title']))
        story.append(Paragraph(f'Generated: {timezone.now().strftime("%d %b %Y")}', styles['Normal']))
        story.append(Spacer(1, 12))

        data = [['Date', 'Partner', 'Topic', 'District', 'Attended', 'Expected', 'Rate']]
        for s in qs:
            rate = f'{s.attendance_rate:.0f}%' if s.attendance_rate is not None else '—'
            topic = s.topic[:40] + ('…' if len(s.topic) > 40 else '')
            data.append([
                s.date.strftime('%d %b %Y') if s.date else '—',
                s.partner,
                topic,
                s.district,
                str(s.actual_participants),
                str(s.expected_participants),
                rate,
            ])

        t = Table(data, repeatRows=1, colWidths=[65, 50, 160, 70, 50, 55, 40])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00658C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('ALIGN', (4, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

        doc.build(story)
        buf.seek(0)
        return FileResponse(buf, as_attachment=True, filename='training_summary.pdf', content_type='application/pdf')
