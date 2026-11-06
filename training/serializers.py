from rest_framework import serializers
from .models import TrainingAttendance, TrainingSession


class TrainingAttendanceSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = TrainingAttendance
        fields = ['id', 'participant_name', 'role', 'role_display', 'attended', 'notes']


class TrainingSessionSerializer(serializers.ModelSerializer):
    actual_participants = serializers.IntegerField(read_only=True)
    attendance_rate = serializers.FloatField(read_only=True)
    attendances = TrainingAttendanceSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingSession
        fields = [
            'id', 'partner', 'district', 'region', 'topic', 'facilitator',
            'date', 'duration_hours', 'expected_participants',
            'actual_participants', 'attendance_rate',
            'notes', 'attendances', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TrainingSessionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingSession
        fields = [
            'partner', 'district', 'region', 'topic', 'facilitator',
            'date', 'duration_hours', 'expected_participants', 'notes',
        ]
