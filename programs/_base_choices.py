"""Shared choice constants used across multiple models."""

ORG_CHOICES = [
    ('PHD', 'Partners in Health and Development (PHD)'),
    ('Bandhu', 'Bandhu Social Welfare Society'),
]

# Bandhu beneficiary-ID district codes (handwritten note, 2026-06-20). The
# beneficiary ID is {2-digit district code}-{4-digit serial}. Kept here — not in
# build_bandhu_forms — so the webhook handler can use it WITHOUT importing that
# command module (which pulls in openpyxl, absent in the prod runtime).
BANDHU_DISTRICT_CODE = {
    'Bandarban': '01', 'Chittagong': '02', 'Chattogram': '02',
    'Chandpur': '03', 'Noakhali': '04', 'Sunamganj': '05',
    'Habiganj': '06', 'Manikganj': '07', 'Narayanganj': '08',
    'Dhaka': '09',   # Dhaka KP clinic — the 9th Bandhu code.
}
