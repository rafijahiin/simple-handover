"""Canonical keys for Bangladeshi place names typed by field staff.

The same upazila arrives spelled several ways in one week of submissions:
`Sadullahpur` / `Sadullapur`, `guimara` / `Guimara`, `Panchari` / `Panchhari`,
and sometimes in Bengali (`সাদুল্লাপুর`). Grouping on the raw string splits one
upazila into several map dots and several table rows.

`canon()` folds all of those onto one key by transliterating Bengali to Latin,
then stripping the parts of a transliteration that carry no information:
case, punctuation, the aspiration `h` (ch/chh, gar/garh), and doubled letters.

    canon('Sadullahpur') == canon('Sadullapur') == canon('সাদুল্লাপুর')

It is deliberately lossy and is ONLY a matching key. Always display the raw
spelling the field team typed, never the key.
"""
import unicodedata

# Bengali (and the Bengali digits) to a plain Latin transliteration. Only the
# characters that appear in place names are mapped; anything unmapped is
# dropped by the alphanumeric filter below.
_BN = {
    'অ': 'a', 'আ': 'a', 'ই': 'i', 'ঈ': 'i', 'উ': 'u', 'ঊ': 'u', 'ঋ': 'ri',
    'এ': 'e', 'ঐ': 'oi', 'ও': 'o', 'ঔ': 'ou',
    'ক': 'k', 'খ': 'kh', 'গ': 'g', 'ঘ': 'gh', 'ঙ': 'ng',
    'চ': 'ch', 'ছ': 'chh', 'জ': 'j', 'ঝ': 'jh', 'ঞ': 'n',
    'ট': 't', 'ঠ': 'th', 'ড': 'd', 'ঢ': 'dh', 'ণ': 'n',
    'ত': 't', 'থ': 'th', 'দ': 'd', 'ধ': 'dh', 'ন': 'n',
    'প': 'p', 'ফ': 'ph', 'ব': 'b', 'ভ': 'bh', 'ম': 'm',
    'য': 'j', 'র': 'r', 'ল': 'l',
    'শ': 'sh', 'ষ': 'sh', 'স': 's', 'হ': 'h',
    'ড়': 'r', 'ঢ়': 'rh', 'য়': 'y', 'ৎ': 't',
    'ং': 'ng', 'ঃ': '', 'ঁ': '',
    # vowel signs (matras)
    'া': 'a', 'ি': 'i', 'ী': 'i', 'ু': 'u', 'ূ': 'u', 'ৃ': 'ri',
    'ে': 'e', 'ৈ': 'oi', 'ো': 'o', 'ৌ': 'ou', '্': '',
    '০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4',
    '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9',
}

# Words that carry no identity ("Sadar Upazila" == "Sadar"). Removed only when
# something else remains, so plain "Sadar" survives.
_NOISE = ('upazila', 'upazilla', 'upzila', 'thana', 'pourashava', 'paurashava',
          'municipality', 'district', 'zila', 'jela', 'sadar' 'hq')


# ড় ঢ় য় are composition exclusions in Unicode, so they normally arrive
# DECOMPOSED as base + nukta (U+09BC). Mapping the base alone turns খাগড়াছড়ি
# into 'kagdacdi', which then fails to match 'Khagrachhari'. Fold the pairs
# before the per-character pass.
_NUKTA = '়'
_NUKTA_PAIRS = (('ড' + _NUKTA, 'r'),    # ড় (rra)
                ('ঢ' + _NUKTA, 'rh'),   # ঢ় (rha)
                ('য' + _NUKTA, 'y'))    # য় (yya)


def translit(text):
    """Bengali script to Latin. Latin input passes through untouched."""
    s = unicodedata.normalize('NFC', text or '')
    for pair, latin in _NUKTA_PAIRS:
        s = s.replace(pair, latin)
    s = s.replace(_NUKTA, '')          # any stray nukta carries no sound here
    return ''.join(_BN.get(ch, ch) for ch in s)


def canon(name):
    """Matching key for a place name. Empty string when there is nothing left.

    Folds: Bengali script, case, spaces/punctuation, the aspiration `h`
    (so `Panchari` == `Panchhari`, `Ramgarh` == `Ramgar`), and doubled
    letters (`Sadullapur` == `Sadulapur`).
    """
    s = translit(name).lower()
    s = ''.join(ch for ch in s if ch.isalnum())
    if not s:
        return ''
    for noise in _NOISE:
        if s.endswith(noise) and len(s) > len(noise):
            s = s[:-len(noise)]
    # Aspiration is the biggest source of variant spellings; drop it, but keep
    # a leading h (Habiganj) so the name does not vanish.
    s = s[0] + s[1:].replace('h', '')
    # Drop vowels after the first letter. Bengali does not write the inherent
    # vowel, so রামগড় transliterates to 'ramgr' while the Latin spelling is
    # 'Ramgarh' -> matching on vowels can never work across the two scripts.
    # This also folds the well-known Latin variants: Barisal/Borishal,
    # Comilla/Cumilla, Jessore/Jashore, Nagarpur/Nagorpur.
    s = s[0] + ''.join(ch for ch in s[1:] if ch not in 'aeiou')
    out = []
    for ch in s:
        if not out or out[-1] != ch:      # collapse doubles
            out.append(ch)
    return ''.join(out)


def canon_pair(district, upazila):
    """'<district-key>|<upazila-key>' — upazila names repeat across districts."""
    return '%s|%s' % (canon(district), canon(upazila))
