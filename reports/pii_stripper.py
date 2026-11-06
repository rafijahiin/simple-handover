"""
Strip personally identifiable information from raw KoboSubmission data
before including it in exported reports.

PII keys confirmed by CIPRB — extend this list as more forms are onboarded.
"""
import re

# PII keys to drop entirely. Audit FIX M1 — extended to match every PII
# field actually used across the models (GBV survivor/perpetrator, fistula
# patient, MPDSR deceased, counselling client, referral) and now matched on
# a normalised key (case- and separator-insensitive) so `Patient Name`,
# `patient-name` and `patient_name` are all caught.
_PII_KEYS = frozenset({
    # generic
    'name', 'fullname', 'address', 'current_address', 'permanent_address',
    'nid', 'nidnumber', 'phone', 'phonenumber', 'mobile', 'mobilenumber',
    'contact', 'contactnumber',
    # patient / respondent / client
    'patient_name', 'patient_id', 'patientid', 'respondent_name',
    'client_name', 'informant_name',
    # family
    'mother_name', 'father_name', 'husband_name', 'guardian_name', 'spouse_name',
    # GBV
    'survivor_name', 'survivor_contact', 'survivor_address',
    'perpetrator_name', 'perpetrator_address',
})

_PHONE_RE = re.compile(r'\b(?:\+?880|0)1[3-9]\d{8}\b')
_NID_RE = re.compile(r'\b\d{10,17}\b')


def _norm(key: str) -> str:
    """Normalise a key for PII matching: lowercase, strip _ - and spaces."""
    return re.sub(r'[\s_\-]', '', key.lower())


# Normalise the PII key set the same way so `patient_name`, `Patient Name`
# and `patientname` all match a single canonical form.
_PII_KEYS_NORM = frozenset(_norm(k) for k in _PII_KEYS)


def _redact_str(value: str) -> str:
    value = _PHONE_RE.sub('[REDACTED]', value)
    value = _NID_RE.sub('[REDACTED]', value)
    return value


def strip_pii(data):
    """
    Recursively strip PII from a dict (or list of dicts) sourced from a Kobo
    `raw_data` blob. PII-named keys are dropped entirely; phone/NID patterns
    in surviving string values are replaced with [REDACTED]. Nested dicts and
    lists (Kobo repeat groups) are recursed (audit FIX M1 — previously only
    a shallow top-level pass, so PII inside repeat groups leaked).
    """
    if isinstance(data, list):
        return [strip_pii(item) for item in data]
    if not isinstance(data, dict):
        return _redact_str(data) if isinstance(data, str) else data

    cleaned = {}
    for key, value in data.items():
        if _norm(key) in _PII_KEYS_NORM:
            continue
        if isinstance(value, (dict, list)):
            cleaned[key] = strip_pii(value)
        elif isinstance(value, str):
            cleaned[key] = _redact_str(value)
        else:
            cleaned[key] = value
    return cleaned
