"""Enketo form URLs per FormType — used by rejection notifications so the
field worker gets a direct "resubmit a corrected entry" link.

Phase 2 (path A): KoboToolbox submissions are immutable, so a rejected
record stays as the audit trail and the worker submits a NEW corrected
entry via the same Enketo form. These links point at those forms.

Mirror of docs/field-onboarding/FORMS_BY_ROLE.md and frontend Spine.tsx.
"""
from .models import FormType

ENKETO_URLS = {
    FormType.MPDSR: 'https://ee.kobotoolbox.org/x/ZOBX0pKd',
    FormType.FISTULA: 'https://ee.kobotoolbox.org/x/MHkEKfzl',
    FormType.BASELINE: 'https://ee.kobotoolbox.org/x/MTvoZ3Hz',
    FormType.FISTULA_STAGED: 'https://ee.kobotoolbox.org/x/mc06MRIn',
    FormType.MPDSR_RESPONSE_PLAN: 'https://ee.kobotoolbox.org/x/7kAJGedj',
}


def resubmit_url(submission) -> str:
    """Best-effort Enketo URL for re-entering a corrected submission."""
    return ENKETO_URLS.get(submission.form_type, '')
