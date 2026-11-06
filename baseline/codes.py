"""Non-answer codes on NUMERIC baseline fields.

Some numeric questions carry a magic value meaning "the respondent did not give a
number" — B108 spells it out in the question text itself: "(99 = Prefer not to
say)". Those are CODES, not quantities. Feeding them to a mean/median/band reports
a refusal as an income of 99 taka: three FSW respondents who declined were being
published as earning under 5,000.

Every entry below was read off the DEPLOYED Kobo forms (asset
aVsJ7VJ35k8GshpQpnXygC / aBT7aCL9p4FGcW4WwXZcr6), not from a local copy — see the
label quoted beside each. Add a field here the moment a questionnaire documents a
code for it; `test_non_answer_codes_match_the_live_forms` guards the mapping.

Only fields whose label documents a code are listed. Do NOT invent codes for
fields that don't declare them: a real answer of 98 would then vanish silently.
"""

NON_ANSWER_CODES: dict[str, dict[str, set[int]]] = {
    'fsw': {
        # "B104 ‡ At what age did you first start providing sexual services?
        #  (Record as stated) (99 = Prefer not to say)"
        'b104': {99},
        # "B108 In the past month, how much total income have you earned from
        #  providing sexual services? (99 = Prefer not to say)"
        'b108': {99},
        # "Q4.1 ‡ At what age did you first join this profession?
        #  (98 = Don't remember  99 = Prefer not to say)"
        'q4_1': {98, 99},
        # "Q4.2 ‡ On the last day you worked, how many clients did you serve?
        #  (99 = Prefer not to say)"
        'q4_2': {99},
        # "Q4.3 Typically, how many clients do you serve in one week?
        #  (97 = Varies too much to say  99 = Prefer not to say)"
        'q4_3': {97, 99},
    },
    'hijra': {
        # "Q4.2 ‡ How old were you the first time you had sex?
        #  (Don't remember = 98, Decline to answer = 99)"
        'q4_2': {98, 99},
    },
}


def is_non_answer(population, field, value) -> bool:
    """True when `value` is a documented non-answer code for this field, so it must
    be excluded from any average, median, band or total."""
    codes = NON_ANSWER_CODES.get(population, {}).get(field)
    if not codes:
        return False
    try:
        return int(float(value)) in codes
    except (TypeError, ValueError):
        return False
