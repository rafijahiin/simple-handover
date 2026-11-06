from rest_framework import serializers
from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    report_type_display      = serializers.CharField(source='get_report_type_display', read_only=True)
    format_display           = serializers.CharField(source='get_format_display', read_only=True)
    period_type_display      = serializers.CharField(source='get_period_type_display', read_only=True)
    narrative_source_display = serializers.CharField(source='get_narrative_source_display', read_only=True)
    web_url                  = serializers.SerializerMethodField()

    def get_web_url(self, obj):
        """Absolute shareable link for web reports; empty for other formats."""
        if obj.report_type == 'web_report' and obj.share_token:
            request = self.context.get('request')
            path = f'/r/{obj.share_token}/'
            return request.build_absolute_uri(path) if request else path
        return ''

    class Meta:
        model = Report
        fields = [
            'id', 'report_type', 'report_type_display',
            'format', 'format_display',
            'partner',
            'year', 'month',
            'period_type', 'period_type_display',
            'period_start', 'period_end',
            'title', 'narrative',
            'narrative_source', 'narrative_source_display', 'model_used',
            'file', 'share_token', 'web_url', 'generated_by', 'created_at',
        ]
        read_only_fields = [
            'id', 'narrative', 'narrative_source', 'narrative_source_display',
            'model_used', 'file', 'generated_by', 'created_at',
        ]


class GenerateReportSerializer(serializers.Serializer):
    report_type  = serializers.ChoiceField(choices=['monthly_summary', 'one_pager', 'newsletter'])
    format       = serializers.ChoiceField(choices=['pdf', 'docx', 'pptx'])
    partner      = serializers.CharField(max_length=20, required=False, default='', allow_blank=True)

    # Period selection
    period_type  = serializers.ChoiceField(
        choices=['biweekly', 'monthly', 'quarterly'],
        default='monthly',
    )
    # For monthly / quarterly: provide the anchor month
    year         = serializers.IntegerField(min_value=2020, max_value=2100, required=False)
    month        = serializers.IntegerField(min_value=1, max_value=12, required=False)
    # For bi-weekly: provide explicit date range
    period_start = serializers.DateField(required=False)
    period_end   = serializers.DateField(required=False)

    include_narrative = serializers.BooleanField(default=True)
