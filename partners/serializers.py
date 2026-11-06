from rest_framework import serializers
from .models import Partner


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ['id', 'code', 'name', 'name_bangla', 'color_hex', 'is_active']
        read_only_fields = ['id']
