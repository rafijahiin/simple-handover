from django.urls import path
from .webhook import programs_webhook, programs_webhook_phd, programs_webhook_bondhu, programs_webhook_by_form

urlpatterns = [
    # ── Recommended: form slug in URL ─────────────────────────────────────
    # Bypasses _xform_id_string entirely — works even when KoboToolbox
    # auto-generates its own id_string on upload.
    #
    # KoboToolbox REST Service setup per form:
    #   URL:    https://<domain>/webhook/programs/form/<form_slug>/
    #   Method: POST
    #   Header: Authorization: Token REDACTED
    #
    # Form slugs:
    #   spondon_client_reg_v1    spondon_clinic_visit_v1   spondon_hiv_sti_test_v1
    #   spondon_adr_record_v1    spondon_autoclave_log_v1  spondon_antenatal_card_v1
    #   spondon_htc_counsel_v1   spondon_counselling_v1    spondon_mh_screening_v1
    #   spondon_gbv_case_v1      spondon_outreach_v1       spondon_group_edu_v1
    #   spondon_referral_v1      spondon_hygiene_kit_v1    spondon_training_event_v1
    #   spondon_coord_meeting_v1 spondon_mobile_camp_v1
    path('form/<str:form_slug>/', programs_webhook_by_form, name='programs-webhook-by-form'),

    # ── Org-specific endpoints (legacy) ───────────────────────────────────
    path('PHD/',    programs_webhook_phd,    name='programs-webhook-phd'),
    path('Bandhu/', programs_webhook_bondhu, name='programs-webhook-bandhu'),

    # ── Shared fallback — org + form type both from payload ───────────────
    path('', programs_webhook, name='programs-webhook'),
]
