"""Which income figure applies to a respondent — resolved from the FORM's branch.

The Hijra instrument asks income twice, on mutually exclusive branches of B101
("who do you currently live with"), and the two are different quantities:

    B101 = '2' (dera)  -> B106 = B104 - (B105 / B103)   PERSONAL income
    B101 != '2'        -> B107 total (sum of 8 sources) HOUSEHOLD earnings

Both totals are `calculate` rows with NO relevance gate, so Kobo evaluates them
for EVERY respondent. B107's expression wraps each source in `if(x!='', x, 0)`,
so a dera resident — who is never shown the B107 block — still submits
`b107_total = 0`. Banding on "value is present" therefore reported 49 dera
residents as households earning under 5,000 taka. A zero here means "not asked",
not "earned nothing", and only the branch can tell those apart.

FSW has no such split: B108 is asked of everyone (and is income FROM SEX WORK,
not total income — the chart title must say so).
"""

_DERA = '2'


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def resolve_income(population, raw):
    """-> (personal, household); either may be None when the branch wasn't asked.

    `raw` must already be flattened to leaf keys.
    """
    if population == 'fsw':
        return _num(raw.get('b108')), None

    if population != 'hijra':
        return None, None

    branch = str(raw.get('b101_live_with') or '').strip()
    if branch == _DERA:
        # B106 is itself guarded (`if b103 > 0`), so it can arrive empty.
        return _num(raw.get('b106_personal_income')), None
    if branch:
        # A genuine 0 is kept: the B107 sources are required on this branch, so
        # all-zeros is an answer. Only the dera branch's phantom 0 is excluded.
        return None, _num(raw.get('b107_total'))
    return None, None
