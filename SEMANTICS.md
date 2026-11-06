# CIPRB dashboard — semantic decisions ledger

Every row below is a choice about **what a term means** on the `/ciprb` dashboard
that is *not* forced by the data and could be wrong. Each was a candidate for the
kind of silent misinterpretation that this month put backwards and fabricated
numbers on the screen (CDN/FDN by place instead of slip; `notified_md = f1+f2`).

**Why this file exists:** a wrong number traced to a *reconciliation* gap is
caught by the reconciliation guard; a wrong number traced to a *meaning* is only
caught by a human who knows the domain. This ledger makes each meaning explicit,
names who owns it, and records whether it is confirmed — so a reviewer can check
the interpretation, not just the arithmetic.

**How it is enforced:** `mpdsr/test_semantics_ledger.py` parses the Ledger table
and asserts every `Anchor` string still exists in its `File`. If code that
implements a decision is rewritten and the anchor disappears, the test fails —
forcing whoever changed it to re-confirm the meaning and update this row, rather
than let the meaning drift unnoticed. Adding a new interpretive decision without
a row here is a review miss, not a test failure.

**Status legend:** `confirmed` = signed off by the named authority;
`pending` = implemented on a best reading, awaiting the authority; `derived` =
the form has no direct question, the value is computed from a documented rule.

---

## Ledger

| Key | Decision | File | Anchor | Authority | Status |
|-----|----------|------|--------|-----------|--------|
| CDN/FDN | Community vs facility notification = **which slip was filed** (Slip 01 = community/CHW, Slip 02 = facility), NOT place of death. Slip 02 has no place field. | mpdsr/views.py | `slip_variant=MPDSRDeathNotification.SLIP_01` | CIPRB (verbatim forms) | confirmed |
| Reporting period | The `/ciprb` period toggle filters on **`created_at`** (when the case entered surveillance), not `date_of_death` — MPDSR reviews deaths retrospectively. | mpdsr/views.py | `created_at__date__gte` | Animesh | pending |
| Reviewed ≠ notified | Review counts and notified counts are **separate sources** and are never derived from each other (the fabricated `notified_md = f1 + f2` is gone). | mpdsr/views.py | `review_counts = {r['sub_form_type']` | CIPRB | confirmed |
| SA maternal-only | The Social Autopsy tile is titled "(Maternal Death)"; it counts **maternal SA re-reviews only** (`sa_md_maternal`), excluding the ~3/17 neonatal autopsies. | mpdsr/views.py | `review_counts['sa_md_maternal']` | Animesh | pending |
| Indicator cohort | The 11 MPDSR "major indicators" are maternal-death indicators from **Form 01 + Form 04 only** (`death_type=maternal AND sub_form_type in f1,f4`); drops f2/f5/sa_md. | mpdsr/views.py | `sub_form_type__in=['f1', 'f4']` | Animesh | confirmed |
| Cause split by form | The two maternal cause-of-death charts split by **source form** (f1 community / f4 facility), NOT place of death. | frontend/src/components/ciprb/MPDSRVisualizations.tsx | `c.sub_form_type === 'f1'` | CIPRB | confirmed |
| f3/f6 excluded | F3 (community stillbirth review) + F6 (facility stillbirth review) are **excluded from every dashboard surface**; rows are retained in the DB for audit. | mpdsr/views.py | `exclude(sub_form_type__in=['f3', 'f6'])` | Animesh | confirmed |
| Reporting-rate denominators | Estimated deaths use fixed ratios per live birth: MD 136/100 000, ND 20/1 000, SB 21/1 000. Reporting rate = notified / estimated. | frontend/src/components/ciprb/MPDSRVisualizations.tsx | `Live Birth × 136` | MPDSR M&E Framework (via CIPRB) | confirmed |
| Neonatal panel cohort | "Neonatal Deaths" counts **all perinatal** cases in scope (f2 + f5 + Social-Autopsy perinatal), f3/f6 excluded. Whether SA perinatal belongs here is open. | mpdsr/views.py | `death_type=DeathType.PERINATAL` | Animesh | pending |
| Place coarsening (review) | Rich per-form place-of-death values are coarsened to HOME / IN_TRANSIT / FACILITY by substring; any unmatched non-empty value → FACILITY. | programs/ciprb_handlers.py | `case.place_of_death = PlaceOfDeath.FACILITY` | CIPRB | confirmed |
| Place coarsening (slip) | Slip-01 place choice → coarse enum: `on_the_way`→IN_TRANSIT, `govt_facility`+`private_ngo`→FACILITY, unmatched→'' (blank, NOT facility). | programs/ciprb_handlers.py | `def _ns_place(payload)` | CIPRB | confirmed |
| Consent | Only an **explicit** consent "No" triggers de-identification (facility/narrative/action-plan withheld). Absent or "unknown" is not a refusal. | programs/ciprb_handlers.py | `consent_refused = (_bool(payload.get('consent_given')) is False)` | CIPRB | confirmed |
| SA death type | Social Autopsy `sa_death_type` 1/2/3 still collapses to MATERNAL(==1) vs PERINATAL(else) for `death_type`, because DeathType has no stillbirth member. The reviewer's actual answer is now preserved verbatim in `sa_death_kind` (maternal/neonatal/stillbirth) so a reviewed stillbirth is no longer indistinguishable from a reviewed neonatal death. | programs/ciprb_handlers.py | `sa_death_kind = {'1': 'maternal', '2': 'neonatal', '3': 'stillbirth'}` | CIPRB | confirmed |
| Stillbirth review route | No STRUCTURED review form accepts a stillbirth: F-02 has no stillbirth field, F-05 records live-born neonates only. The Social Autopsy form does (`sa_death_type` 3, মৃতজন্ম on the paper tool), so that is the only stillbirth review pathway and `review_counts['sb_reviewed']` is its count. | mpdsr/views.py | `review_counts['sb_reviewed']` | CIPRB | confirmed |
| Social Autopsy cohort | `social_autopsy.total` is the MATERNAL subset only, matching the section title and the dashboard tile. The full cohort is `all_kinds_total` with a `by_kind` split. They previously disagreed (15 vs 18 on the same page) because the tile filtered to maternal and this block did not. | mpdsr/views.py | `sa_qs = sa_all_qs.filter(death_type=DeathType.MATERNAL)` | CIPRB | confirmed |
| Indicator label decoding | Indicator breakdowns are decoded from raw form codes to English labels at the aggregate, and legacy label variants merge with their form code ('normal' + 'vaginal_spontaneous' → one bucket). Rendering raw is what showed `doctor_mbbs`/`upazila_hc` to CIPRB and split one fact across two slices. | mpdsr/code_labels.py | `def relabel(field, counts)` | CIPRB | confirmed |
| Time of death | Stored as a **clock time**, not a phase of pregnancy (the model comment saying antepartum/intrapartum is historical). Binned into six four-hour periods; charting it raw produced 46 timestamps at 2% each. | mpdsr/code_labels.py | `def band_time_of_death(counts)` | CIPRB | confirmed |
| PNC is a count | `pnc_received` holds a VISIT COUNT, not yes/no. 99 is the forms' not-known sentinel; >10 is a data-entry error and is surfaced as "Invalid entry" rather than charted as real. | mpdsr/code_labels.py | `def band_pnc(counts)` | CIPRB | confirmed |
| Fistula stage monotonic | `current_stage` never regresses — a later-arriving earlier-stage submission does not roll the case back; underpins the cumulative funnel. | programs/ciprb_handlers.py | `stage_order` | CIPRB | confirmed |
| Baseline indicator | The home "Baseline records entered" indicator counts verified `BaselineResponse` rows (post-verification) — replacing a broken import of a deleted model. | indicators/ciprb.py | `from baseline.models import BaselineResponse` | CIPRB | confirmed |
| District canonicalisation | District slugs are Title-cased so live submissions match seed/Excel rows (all 18 CIPRB districts are single words). | programs/ciprb_handlers.py | `raw.replace('_', ' ').title()` | CIPRB | confirmed |
| MNM primary cause | The Near-Miss "primary cause" is **derived** (the form has no single primary-cause question): first "present" item in a fixed clinical-priority order. | programs/ciprb_handlers.py | `_MNM_CAUSE_PRIORITY` | CIPRB | derived |
| MNM screening flag | WHO 0–4 criterion codes collapse to a boolean: 1/2/3 → True (present at some point), 0 → False, 4/blank → None (unknown). | programs/ciprb_handlers.py | `def _mnm_flag(v)` | WHO MNM (via CIPRB) | confirmed |
| facility_totals null | An empty `MPDSRFacilityCount` returns `facility_totals = None` (not a truthy zero-dict) so the frontend fallback to live slips actually fires. | mpdsr/views.py | `facility_totals = None` | CIPRB (correctness contract) | confirmed |
| Notification source pref | The CDN/FDN level panel prefers Sayeed's Excel ingest when present (whole-programme), falling back to live Kobo slips when the table is empty. | mpdsr/views.py | `notification_by_level_source` | Animesh | confirmed |

---

## Open items (status = pending) — need the named authority's sign-off

- **Reporting period = entered surveillance (created_at).** Under death-date
  semantics the contract window would start in January and show different totals.
  Animesh to confirm which the dashboard should mean.
- **SA maternal-only tile** and **SA perinatal in the Neonatal panel.** Whether
  Social-Autopsy re-reviews count alongside the primary review forms is Animesh's
  call; today SA maternal is shown as its own tile and SA perinatal is inside the
  neonatal total.
- The **40-minute baseline interview threshold** (a baseline, not CIPRB-dashboard,
  decision) remains pending Nuruzzaman's pilot timing — tracked separately.
| Reconciliation scope | The daily replay covers CIPRB (static registry) plus every PHD and Bandhu form DISCOVERED from its Kobo webhook (`/webhook/programs/form/<slug>/`). Partner replay is safe because all partner handlers are idempotent (kobo_submission_id dedup / get_or_create on client ID). Baseline forms are deliberately excluded: their pipeline is verification-gated with its own console. | mpdsr/reconcile.py | `def discover_partner_forms` | CIPRB | confirmed |
| Modifiable factor (CIPRB-10) | `MPDSRAction.sub_category` holds master Table 1's sub-category for System-Strengthening actions and (from 2026-08) master Table 2's **common modifiable factor** for the two factor sections; `section` disambiguates the vocabulary. The master ships those factor rows BLANK for districts to fill, so the list is the factors districts actually write plus `other` + free text (stored as typed, truncated to 120). | programs/ciprb_handlers.py | `if section == ActionSection.SYSTEM_STRENGTHENING:` | CIPRB | confirmed |
| Campaign vs case registry | The "Fistula Campaign" panel reports the **daily CHW activity form** (FistulaCampaign: reports, districts/upazilas actually visited, households, population, GPS dots). The case funnel (suspected/diagnosed/referred/repaired/rehabilitated) reports the **patient registry** (CIPRBFistulaCase) and appears ONCE. The two are never merged: a CHW activity day is not a patient, so adding the campaign's own suspected tally to the registry funnel would double-count. Funnel percentages use the PREVIOUS stage as denominator (referral rate is of diagnosed, per CIPRB 3 Aug 2026). | fistula/views.py | `campaign = {` | CIPRB | confirmed |
| Campaign map placement | Campaign dots are placed on the **reported upazila** (centroid from geoBoundaries ADM3), never on the device GPS: 30 of 71 approved reports name a Gaibandha upazila while carrying Khagrachari coordinates, and all 71 collapse onto 6 distinct coordinates. GPS is kept only to flag disagreement >50 km. Rows are grouped on `canon_pair()`, which folds spelling variants and Bengali script onto one key (Sadullahpur = Sadullapur = সাদুল্লাপুর), so one upazila is one dot and one row; the majority raw spelling is displayed and all variants are listed. Phonetic keys that would match two real upazilas in a district (Demra/Dhamrai) are excluded from the atlas and fall back to the district centre. | fistula/geo_names.py | `def canon` | CIPRB | confirmed |
