# Bandhu Subsystem — Build Plan

> ## ⚠ SUPERSEDED — as-built differs from this plan
>
> **This document is a historical planning artifact. The Bandhu subsystem has
> since been built and deployed, and the as-built design differs from the plan
> below in several material ways. Read the code (and migration 0014) as the
> source of truth, not this file.** Key differences:
>
> - **Built, not "plan only".** The "PLAN ONLY — no code written yet" status
>   below is stale; handlers, models, indicators and forms are all implemented
>   (`programs/bandhu_handlers.py`, `programs/management/commands/build_bandhu_forms.py`,
>   `indicators/bandhu.py`).
> - **Unified TG/gender codes**, NOT per-form schemes. Every tool uses one
>   shared `tg_code` list (01 MSM · 02 MSW · 03 FSW · 04 EVA · 05 TG/Hijra ·
>   06 Others) — see `_shared_choices()` in build_bandhu_forms.py.
> - **3 Kobo forms**, not 2 per-form-TG forms: `bandhu_mother_list_v1`
>   (registration), `bandhu_service_log_v1`, `bandhu_activity_ops_v1`.
> - **18 indicators** computed per migration `0014` (compute functions in
>   `indicators/bandhu.py`; indicator 1.4b was retired as a duplicate of 1.1).
>
> Everything below is retained for context only.

---

Project: "Men, Boys & Transgender SRHR response amongst Rohingya & Host Community"
Implementer: Bandhu Social Welfare Society · Funder: UNFPA
Status: **PLAN ONLY — no code written yet. Awaiting approval.**

Decisions locked with Rafi (2026-06-08):
- **TG/gender codes: keep per-form schemes** (replicate each paper register's own
  code list exactly; a translation layer handles cross-tool rollups).
- **Form model: follow the PHD system** — aggregate daily-tally Kobo forms for
  service logbooks; case-level encrypted forms for sensitive HIV/GBV; CSV
  `pulldata()` autofill for client/centre lookups; webhook → manager approval →
  dashboard, exactly as PHD.

Reuse target: the PHD pipeline is the template throughout. Bandhu = a parallel
org inside the SAME Django app + same dashboard, new subpage. No new services.

---

## 1. Source tools → system artifacts

16 paper tools (UNFPA Tools.xlsx). F-14 is empty; tool-9 & tool-14 formats are
undesigned (flag to Animesh). Each tool maps to a Kobo form + handler + model.

| Tool | Register | Submission model | Sensitivity |
|---|---|---|---|
| F-01 | Wellness Center Service Logbook | Daily aggregate tally / centre | normal |
| F-02 | GBV Register | **Case-level, encrypted** | sensitive |
| F-03 | Mental Health Counseling Register | Case-level (session) | sensitive |
| F-04 | Daily Outreach Monitoring | Daily aggregate / outreach worker | normal |
| F-05 | Patient Record Register (clinical/STI) | Case-level | normal |
| F-06 | HTC Service Register | **Case-level, encrypted** | sensitive |
| F-07 | KP Clinic Information | Roster (seed, rarely changes) | normal |
| F-08 | Detailed HIV-identified (HIV+/ART) | **Case-level, encrypted** | highly sensitive |
| F-09 | Wellness Center Information | Roster (seed) | normal |
| F-10 | Mobile Health Camp Register | Case-level (mirror of F-05) | normal |
| F-11 | Attendance Sheet | Per-event roster | normal |
| F-12 | Event Report | Per-event narrative + tally | normal |
| F-13 | Stock Register | Per-item ledger entry | normal |
| Referral Reg. | Referral Register | Case-level + follow-up dates | normal |
| Counseling | Daily Counseling form | Daily aggregate / centre | normal |
| F-14 | (empty) | — design w/ Animesh | — |

Encrypted case-level forms (F-02, F-06, F-08) follow the **fistula tracker**
encryption pattern already in the codebase, not plain models.

## 2. Canonical reference data (seed commands)

- `seed_bandhu_centres.py` — Wellness Centers (F-09) + KP Clinic (F-07) +
  cruising spots, keyed to the 8 districts (Sunamganj, Bandarban, Chandpur,
  Noakhali, Chittagong, Narayanganj, Habiganj, Manikganj). Mirrors
  `seed_centers.py` (PHD).
- **TG code tables** — one Python dict PER scheme (3 schemes), single-sourced in
  one module `bandhu_codes.py`, plus a `TG_CANONICAL` map and `to_canonical()`
  translator used only at aggregation time. Forms keep their native codes.

## 3. Kobo forms (management command `build_bandhu_forms.py`)

Mirrors `build_phd_forms.py`: generates XLSForms, `--upload` imports + redeploys
to Kobo, sets REST webhook with `?token=<KOBO_WEBHOOK_SECRET>`.

- Aggregate tally forms: F-01, F-04, Counseling (select centre via
  `select_one` from seeded list; daily counts per service column).
- Case-level forms: F-02, F-03, F-05, F-06, F-08, F-10, Referral.
- Client autofill via `pulldata()` from `bandhu_clients.csv` (UID → demographics),
  auto-synced on client save exactly like `export_phd_clients.py` + the Kobo
  attachment sync.
- Event/roster forms: F-11, F-12, F-13, F-07, F-09.

## 4. Backend (Django — new app `bandhu` or extend `programs`)

- Models per tool (normal) + encrypted models (F-02/F-06/F-08).
- `bandhu_handlers.py` — `FORM_HANDLERS` dispatch keyed on `id_string`, reusing
  `_flatten_group_keys` and a `_district()` canonicaliser (copy CIPRB pattern).
- Submissions land as **pending**, visible to Bandhu managers only (org scoping
  already enforced by `get_queryset`), approve → live.
- Indicator endpoints: target-vs-actual against the **monthly milestones**
  (Jun/Jul/Aug/Sep 2026) from the MIS Requirements sheet — same engine as the
  PHD progress tracker.

## 5. Indicator → tool mapping (from MIS Requirements)

| # | Indicator (abridged) | Target | Source tool(s) |
|---|---|---|---|
| 1.2.1.1 | KP receiving HIV/STI screening, counselling, FP | 4000 | F-01, F-05 |
| 1.2.2 | GBV survivors screened/first-line/referred | 120 | F-02 |
| 1.3.3 | MHPSS counselling sessions | 48 | F-03 |
| 1.2.1.3a | Outreach/health-ed sessions conducted | 480 | F-04 |
| 1.2.1.3b | KP reached via outreach | 4000 | F-04 |
| — | STI services | 2000 | F-05 |
| — | HIV tests | 2000 | F-06 |
| 14 | KP clinic supported | 1 | F-07 |
| 1.9.2 | KP referred & linked to ART | 25 | F-08, Referral |
| 16 | Drop-in centers established | 8 | F-09 (+tool-9 fmt) |
| 1.11.1 | Mobile health camps | 40 | F-10 |
| 18 / 2.3.1 | Managers / providers oriented-trained | 192 / 192 | F-11, F-12 |
| 2.5.2 / 4.0 | Coordination meetings | 16 / 16 | F-12 |
| 2.8.1 | Community leaders/peer educators trained | 160 | F-11 |
| 2.9 | Observance events | 2 | F-12 |
| 7 | IEC/SBCC materials disseminated | 16800 | F-13 |
| 8 | e-billboards / printed billboards | 40+16 | tool-14 fmt (TBD) |

## 6. Frontend (Bandhu subpage)

Reuse PHD subpage components: `IndicatorGrid` (heading "UNFPA Framework"),
`TargetConfig`, headline cards, by-centre breakdown, map plotted on the 8
districts. Nav item gated to Bandhu org + admins (copy PHD `visible` predicate).
Bangla labels alongside English (forms already bilingual on paper).

## 7. Open items to flag to Dr. Animesh (M&E review step)

1. **3 conflicting TG/gender code schemes** — confirm we replicate each per-form
   (current decision) vs adopt one master list.
2. **Geographic scope** — requirements say 8 named districts; several tool
   headers say "Rohingya & Host Community" (Cox's Bazar). Which governs?
3. **F-14 empty**, **tool-9 "new format"**, **tool-14 "screen shoot"** — formats
   undesigned; need definitions before building those forms.
4. Encryption scope confirmation for F-02/F-06/F-08 (HIV/GBV case data).

## 8. Phasing (mirrors CIPRB/PHD delivery)

- **P0** Seed data + canonical code module + 8-district map data.
- **P1** Aggregate forms (F-01, F-04, Counseling) + handlers + Bandhu subpage shell.
- **P2** Case-level + encrypted forms (F-02/03/05/06/08/10/Referral) + approvals.
- **P3** Event/roster/stock (F-07/09/11/12/13) + indicator wiring to monthly targets.
- **P4** Audit + Kobo run-proof (live webhook) + UAT rows, same as PHD/CIPRB.
