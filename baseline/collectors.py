"""Baseline data-collector roster — the single source of truth for code → name.

The Kobo forms ask "Data Collector" as a `select_one` (field `dc_code`), so a
submission stores only the CODE ('1', '2', …), never the name. Two consumers need
this mapping and MUST stay in sync:

  * programs/management/commands/build_baseline_forms.py — generates the
    `dc_hijra` / `dc_fsw` choice lists in the XLSForms from this dict.
  * baseline/monitoring.py — resolves the submitted `dc_code` back to the
    enumerator's name for the field-team roster (otherwise the dashboard shows
    "1", "2", "3" instead of names).

Keep the codes stable: they are already stored in submitted data. Add new
enumerators with the next unused code, and REBUILD + REDEPLOY the forms
(`python manage.py build_baseline_forms` then `railway run python
_deploy_baseline.py <hijra|fsw>`) so the dropdown offers them.

CIPRB (Abdullah / Dr. Sayeed) owns this roster.
"""

DATA_COLLECTORS: dict[str, dict[str, str]] = {
    'hijra': {
        '1': 'Md. Abdullah-Al-Mahbub',
        '2': 'Md. Mamun Hawlader',
        '3': 'Kamal Hossain',
        '4': 'Md Shajjadul Islam Shagor',
        '5': 'Golam Dastagir Sunny',
        '6': 'Moklesur Rahman',
        '7': 'Md. Iqbal Hossain',
        '8': 'Md. Saiful Islam',
        '9': 'Golam Mehedi',
        '10': 'Md. Firoz',
        '11': 'Md. Awlad Hossain Ahmmad',
        '12': 'Md. Mahbubul Huq',
    },
    'fsw': {
        '1': 'Mst. Mahfuza Sultana',
        '2': 'Dipty Biswas',
        '3': 'Pakhi Akter',
        '4': 'Nargis Khanam',
        '5': 'Sabita Rani Halder',
        '6': 'Zannatul Ferdous Khan',
        '7': 'Aparna Rani Dey',
    },
}


def collector_name(population: str, code) -> str:
    """'hijra', '3' -> 'Kamal Hossain'. Unknown code/population -> ''."""
    if code in (None, ''):
        return ''
    return DATA_COLLECTORS.get((population or '').lower(), {}).get(str(code).strip(), '')
