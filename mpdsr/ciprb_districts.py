"""The CIPRB working districts.

The canonical list lives in the Kobo form builder
(programs/management/commands/build_ciprb_forms.py, CIPRB_DISTRICTS) because
that is what the field forms offer in their district dropdown. That module
imports openpyxl at module level and must never be imported at request time,
so the list is mirrored here for the API to use.

The mirror is not free: two copies drift. A test asserts the two are identical,
so a district added to the forms and not here fails the build rather than
quietly disappearing from a dashboard panel.
"""

CIPRB_DISTRICTS = (
    'Sunamganj', 'Sherpur', 'Bhola', 'Kurigram', 'Gaibandha',
    'Khagrachari', 'Noakhali', 'Patuakhali', 'Sirajganj', 'Barguna',
    'Jamalpur', 'Bagerhat', 'Habiganj', 'Moulavibazar', 'Sylhet',
    'Bandarban', 'Chandpur', 'Rangpur', 'Dhaka',
)

CIPRB_DISTRICTS_LOWER = frozenset(d.lower() for d in CIPRB_DISTRICTS)


def is_ciprb_district(name: str) -> bool:
    return (name or '').strip().lower() in CIPRB_DISTRICTS_LOWER
