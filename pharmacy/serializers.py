"""Serializer for PrescriptionRecord — enforces the same cap as the model."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import PrescriptionRecord, max_quantity_for


class PrescriptionRecordSerializer(serializers.ModelSerializer):
    partner_code = serializers.CharField(source='partner.code', read_only=True)
    center_name = serializers.CharField(source='center.name', read_only=True)
    prescribed_by_email = serializers.CharField(
        source='prescribed_by.email', read_only=True, allow_null=True,
    )
    drug_display = serializers.CharField(source='get_drug_display', read_only=True)
    condition_display = serializers.CharField(
        source='get_condition_type_display', read_only=True,
    )

    class Meta:
        model = PrescriptionRecord
        fields = [
            'id', 'client_id',
            'partner', 'partner_code',
            'center', 'center_name',
            'prescribed_by', 'prescribed_by_email',
            'date', 'drug', 'drug_display',
            'quantity', 'condition_type', 'condition_display',
            'approval_status', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            # Server-set — never accept these from the request body (cross-org
            # forgery + self-approval prevention; see PrescriptionRecordViewSet).
            'partner', 'approval_status', 'prescribed_by',
            'partner_code', 'center_name', 'prescribed_by_email',
            'drug_display', 'condition_display',
        ]

    def validate(self, attrs):
        """Re-enforce the drug-quantity cap at the API layer.

        Mirrors PrescriptionRecord.clean() — never silently caps; always
        returns a 400 with a user-facing message identifying the cap."""
        # For PATCH, fall back to existing instance values when fields
        # are not supplied.
        instance = self.instance
        drug = attrs.get('drug', getattr(instance, 'drug', None))
        condition = attrs.get(
            'condition_type', getattr(instance, 'condition_type', None),
        )
        quantity = attrs.get(
            'quantity', getattr(instance, 'quantity', None),
        )

        if quantity is None or quantity <= 0:
            raise serializers.ValidationError(
                {'quantity': 'Quantity must be a positive integer.'}
            )

        try:
            max_qty, unit = max_quantity_for(drug, condition)
        except DjangoValidationError as exc:
            # Surface model-level errors as DRF errors verbatim.
            raise serializers.ValidationError(exc.message_dict)

        if quantity > max_qty:
            raise serializers.ValidationError({
                'quantity':
                    f'{drug} ({condition}) capped at {max_qty} {unit}. '
                    f'Requested {quantity} {unit} — submission rejected.',
            })
        return attrs
