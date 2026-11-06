from rest_framework import serializers

from .models import IndicatorTarget, KoboFormMapping


class KoboFormMappingSerializer(serializers.ModelSerializer):
    partner_code = serializers.CharField(source='partner.code', read_only=True, allow_null=True)

    class Meta:
        model = KoboFormMapping
        fields = [
            'id', 'form_slug', 'form_label', 'partner', 'partner_code',
            'kobo_asset_uid', 'is_active', 'notes',
        ]
        read_only_fields = ['id']


class IndicatorTargetSerializer(serializers.ModelSerializer):
    """Read+write serializer for /api/indicators/targets/.

    `partner` is exposed both as the FK id (for writes) and as a denormalised
    `partner_code` and `partner_color` (for the frontend's grouped render).
    `updated_by` is read-only — the view's perform_update sets it from
    request.user."""
    partner_code = serializers.CharField(source='partner.code', read_only=True)
    partner_color = serializers.CharField(source='partner.color_hex', read_only=True)
    source_form_slug = serializers.CharField(
        source='source_form.form_slug', read_only=True, allow_null=True,
    )
    updated_by_email = serializers.CharField(
        source='updated_by.email', read_only=True, allow_null=True,
    )

    class Meta:
        model = IndicatorTarget
        fields = [
            'id',
            'partner', 'partner_code', 'partner_color',
            'objective_number',
            'activity_code', 'activity_label',
            'indicator_label',
            'target_value', 'unit',
            # Animesh spec — UNFPA-set monthly splits, same model as the
            # overall target_value. List of {month: "YYYY-MM", target: <num>}.
            'monthly_targets',
            'source_form', 'source_form_slug',
            'notes', 'is_active',
            'created_at', 'updated_at',
            'updated_by', 'updated_by_email',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'updated_by', 'updated_by_email',
            'partner_code', 'partner_color', 'source_form_slug',
        ]


class IndicatorProgressSerializer(serializers.Serializer):
    """Read-only serializer for computed indicator progress (Step 3 shape).

    Emitted by `service.get_partner_indicator_progress` — one dict per
    IndicatorTarget row for the requested partner. Fields:

      activity_code     canonical fixture code, e.g. '1.4a' / 'OVERALL'
      objective_number  0–4 (0 = PHD overall, no Bandhu 3)
      activity_label    long-form activity description from the fixture
      indicator_label   one-line indicator wording
      target_value      float or null (null = "Not Set")
      unit              'individuals' / 'sessions' / 'pcs' / ...
      achievement       always a number; 0 if no records yet
      percentage        null if target null; 0 if achievement=0 vs target>0;
                        else round(achievement / target * 100, 1)
      unlinked          True if no compute function exists yet for this
                        activity_code (module not built) — UI still renders
                        the row, badged "Module pending"
      organisation      added by the view layer for the all-orgs roll-up
    """
    activity_code = serializers.CharField()
    objective_number = serializers.IntegerField()
    activity_label = serializers.CharField(allow_blank=True)
    indicator_label = serializers.CharField()
    target_value = serializers.FloatField(allow_null=True)
    unit = serializers.CharField()
    achievement = serializers.FloatField()
    percentage = serializers.FloatField(allow_null=True)
    unlinked = serializers.BooleanField()
    organisation = serializers.CharField(required=False, allow_blank=True)
    # Monthly cadence (Animesh spec) — set explicitly by UNFPA via
    # IndicatorTarget.monthly_targets JSON; null = "Not set" until UNFPA
    # configures it in Target Config.
    month_label = serializers.CharField(allow_null=True, required=False)
    month_target = serializers.FloatField(allow_null=True, required=False)
    month_achievement = serializers.FloatField(allow_null=True, required=False)
    month_percentage = serializers.FloatField(allow_null=True, required=False)
