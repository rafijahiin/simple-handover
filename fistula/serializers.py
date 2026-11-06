from rest_framework import serializers
from .models import FistulaCampaign, FistulaCornerCase, FistulaCampaignVisit


class FistulaCampaignSerializer(serializers.ModelSerializer):
    """Legacy aggregate campaign session (one row per CHW day)."""
    class Meta:
        model = FistulaCampaign
        fields = [
            'id', 'case_hash', 'partner',
            'district', 'upazila', 'union', 'village', 'facility_name', 'region',
            'campaign_date',
            'households_visited', 'population_covered',
            'women_screened', 'women_reached_awareness', 'men_reached_awareness',
            'community_sessions',
            'suspected_fistula_cases', 'confirmed_fistula_cases',
            'new_cases', 'repeat_cases',
            'fistula_type', 'fistula_cause',
            'cases_referred', 'cases_accepted_referral', 'cases_reached_facility',
            'cases_surgery_completed', 'cases_surgery_pending', 'cases_surgery_not_eligible',
            'cases_followup_due', 'cases_followup_completed', 'cases_lost_followup',
            'cases_counselling_provided', 'cases_social_reintegration',
            'main_barriers', 'notes',
            'latitude', 'longitude',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'case_hash', 'partner', 'district', 'upazila', 'union', 'village',
            'facility_name', 'region', 'campaign_date',
            'women_screened', 'women_reached_awareness', 'men_reached_awareness',
            'community_sessions', 'suspected_fistula_cases', 'confirmed_fistula_cases',
            'new_cases', 'repeat_cases', 'fistula_type', 'fistula_cause',
            'cases_referred', 'cases_accepted_referral', 'cases_reached_facility',
            'cases_surgery_completed', 'cases_surgery_pending', 'cases_surgery_not_eligible',
            'cases_followup_due', 'cases_followup_completed', 'cases_lost_followup',
            'cases_counselling_provided', 'cases_social_reintegration',
            'latitude', 'longitude', 'created_at',
        ]


class FistulaCornerCaseSerializer(serializers.ModelSerializer):
    """Per-patient diagnosis at District Hospital Fistula Corner.

    PII (patient_name, husband_name, mobile_number) round-trips through
    the EncryptedCharField — plaintext on POST, plaintext on GET, stored
    encrypted at rest."""
    class Meta:
        model = FistulaCornerCase
        fields = [
            'id', 'case_hash',
            # PII
            'patient_name', 'husband_name', 'mobile_number',
            # Non-PII patient
            'age_years',
            # Address
            'village', 'union', 'upazila', 'district',
            # Dates
            'suspected_date', 'identification_date', 'diagnosis_date',
            # Informant
            'informant_name', 'informant_designation',
            # Clinical
            'suffering_duration', 'fistula_cause', 'fistula_type',
            # Provider
            'service_provider_name', 'service_provider_designation',
            # Referral
            'referral_date', 'referral_place', 'surgery_performed', 'surgery_outcome', 'referral_outcome',
            # Rehabilitation (Animesh's definition: any support = rehabilitated)
            'received_rehab_support', 'rehab_support_types', 'rehab_support_date',
            # Remarks
            'remarks',
            # Provenance
            'latitude', 'longitude',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'case_hash', 'created_at', 'updated_at']


class FistulaCampaignVisitSerializer(serializers.ModelSerializer):
    """Per-suspected-case household screening row."""
    class Meta:
        model = FistulaCampaignVisit
        fields = [
            'id', 'case_hash',
            'visit_date',
            # PII
            'patient_name', 'husband_name', 'contact_number',
            # Non-PII
            'age_years', 'education', 'profession', 'husband_profession',
            # Address
            'village', 'union', 'upazila', 'district', 'from_haor',
            # Clinical / history
            'delivery_mode', 'delivery_outcome', 'suffering_duration', 'info_source',
            # Remarks
            'remarks',
            # Provenance
            'latitude', 'longitude',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'case_hash', 'created_at', 'updated_at']
