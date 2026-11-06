from rest_framework import serializers

from accounts.serializers import UserSerializer
from .models import KoboSubmission


class KoboSubmissionSerializer(serializers.ModelSerializer):
    reviewed_by = UserSerializer(read_only=True)
    form_type_display = serializers.CharField(source='get_form_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Baseline duplication warning (Animesh's spec). For BASELINE submissions
    # only, expose whether the auto-created BaselineSurvey row was flagged as
    # a same-location-same-day duplicate of an existing one. Managers see
    # this on the approval queue and can override.
    is_baseline_duplicate = serializers.SerializerMethodField()
    # MPDSR QA-gate flags (Animesh deck slide 9). Computed from the raw Kobo
    # payload for any MPDSR submission; empty list otherwise. The manager
    # approval queue shows an amber AlertTriangle pill when this list is
    # non-empty so implausible values get scrutinised before approval. If
    # the MPDSRCase has already been materialised (post-approval), prefer
    # the stored flags so dashboards stay consistent.
    logic_flags = serializers.SerializerMethodField()

    def get_is_baseline_duplicate(self, obj) -> bool:
        bs = getattr(obj, 'baseline_survey', None)
        return bool(bs and getattr(bs, 'is_duplicate', False))

    def get_logic_flags(self, obj) -> list[str]:
        from .models import FormType
        if obj.form_type != FormType.MPDSR:
            return []
        existing = getattr(obj, 'mpdsr_case', None)
        if existing is not None and getattr(existing, 'logic_flags', None):
            return list(existing.logic_flags)
        try:
            from mpdsr.validators import compute_flags_from_submission
            return compute_flags_from_submission(obj)
        except Exception:
            # Advisory only — never break the serializer if computation fails.
            return []

    class Meta:
        model = KoboSubmission
        fields = [
            'id', 'kobo_id', 'form_type', 'form_type_display', 'partner',
            'worker_name', 'district', 'region',
            'latitude', 'longitude',
            'submitted_at', 'received_at',
            'status', 'status_display',
            'reviewed_by', 'reviewed_at', 'rejection_reason',
            'review_history',
            'is_baseline_duplicate',
            'logic_flags',
        ]
        read_only_fields = fields


class KoboSubmissionDetailSerializer(KoboSubmissionSerializer):
    """Includes raw_data — only served on retrieve, not list."""

    class Meta(KoboSubmissionSerializer.Meta):
        fields = KoboSubmissionSerializer.Meta.fields + ['raw_data']


class RejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(allow_blank=False)


class ApproveSerializer(serializers.Serializer):
    # Animesh: managers should be able to leave an "ok"/"not ok" note on
    # approval too, not just rejection. Optional.
    note = serializers.CharField(allow_blank=True, required=False, default='')
