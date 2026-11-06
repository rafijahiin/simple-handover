from rest_framework import serializers

from .models import Alert, MonthlyTarget


class MonthlyTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyTarget
        fields = [
            'id', 'partner', 'form_type', 'year', 'month',
            'target', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        month = data.get('month', getattr(self.instance, 'month', None))
        if month is not None and not (1 <= month <= 12):
            raise serializers.ValidationError({'month': 'Month must be between 1 and 12.'})
        return data


class AlertSerializer(serializers.ModelSerializer):
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    alert_type_display = serializers.CharField(source='get_alert_type_display', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id', 'partner', 'alert_type', 'alert_type_display',
            'severity', 'severity_display', 'title', 'message',
            'acknowledged', 'acknowledged_at', 'created_at',
        ]
        read_only_fields = [
            'id', 'alert_type', 'severity', 'title', 'message',
            'acknowledged_at', 'created_at',
        ]
