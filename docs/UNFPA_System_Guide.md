# IDMS / "SIMPLE" — System Guide for UNFPA
### What data comes from where, and how to navigate the site — per partner

> Audience: UNFPA (super-admin, sees all partners). Scope: the live Integrated Digital M&E
> System (Django + DRF backend, React/Vite dashboard, KoboToolbox field forms).
> Prepared from a full code trace (forms → webhooks → handlers → models → API endpoints →
> dashboard charts/`SourceChip`s → routes/access), adversarially re-checked against the codebase.

---

## 0. How to read this guide

Every chart on the dashboard has a **`📄 Source` chip** in its header naming the Kobo form it
draws from. This guide makes the *full* lineage explicit:

```
Field form (KoboToolbox)  →  Webhook  →  Handler  →  Database model  →  API endpoint  →  Chart on the site
```

Three partners, two roles in the data:
- **PHD** and **Bandhu** are **data-entry** partners (field staff submit, managers approve).
- **CIPRB** is **monitoring-only**: its field data lands straight on the dashboard (no approval queue).

---

## 1. The big picture — the universal pathway

```
                 ┌─────────────────────────── KoboToolbox (phones, geo-tagged) ───────────────────────────┐
   Field staff → │  PHD: Registration + Service Log   Bandhu: Mother List + Service Log + Activity/Ops      │
   (no dashboard │  CIPRB: 10 surveillance forms (Fistula, MPDSR ×6, Notification ×2, Near-Miss, Resp.Plan) │
    account)     └──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                                             │  webhook POST (signature-checked, keys flattened)
                                          ┌──────────────────┴───────────────────┐
                       /webhook/programs/ (PHD, Bandhu, CIPRB×9)        /webhook/kobo/ (CIPRB Response Plan only)
                                          │                                       │
                              partner handler upserts                  submissions dispatcher
                          programs.* / fistula.* / mpdsr.*              → MPDSRActionPlanSummary
                                          │
              ┌───────────────────────────┼───────────────────────────┐
        PHD: PENDING               Bandhu: PENDING                CIPRB: visible immediately
        → manager approves         → manager → MANAGER_APPROVED    (no approval queue;
          → APPROVED (1 stage)       → UNFPA → APPROVED (2 stages)  MPDSR review STATUS is
                                                                    editorial, not a gate)
              └───────────────────────────┴───────────────────────────┘
                                          │  charts count APPROVED rows only (PHD/Bandhu)
                                          ▼
                              Dashboard pages (/phd, /bondhu, /ciprb)
```

**The single most important rule for trusting numbers:** PHD and Bandhu headline KPIs and
indicator grids count **only `APPROVED`** rows. For **Bandhu** that means data appears **only
after UNFPA completes the second approval stage**. CIPRB data appears as soon as the webhook saves it.

---

## 2. Roles & access matrix

| Role | Org | Sees | Approval power |
|---|---|---|---|
| **Field staff** | PHD / Bandhu / CIPRB | KoboToolbox only — **no dashboard login** | — |
| **Manager** | PHD | `/approvals` only (redirected there from everywhere) | PHD: PENDING → APPROVED (1 stage) |
| **Manager** | Bandhu | `/approvals` only | Bandhu: PENDING → MANAGER_APPROVED (stage 1) |
| **Org lead / focal** | PHD / Bandhu / CIPRB | Own partner dashboard + tools (reports, tracker, records…) | Can configure own-partner targets |
| **UNFPA** | UNFPA | **All three partners** + all trackers | **Bandhu stage-2 approver** (MANAGER_APPROVED → APPROVED) |
| **CIPRB super-admin** | CIPRB | **All three partners** (monitoring) | — |
| **Developer / Supervisor** | — | Everything (cross-org admin) | Any approval, any partner |

**Route guards (frontend, `App.tsx`):** `RequireOrg(['PHD'])` → `/phd`; `RequireOrg(['Bandhu'])`
→ `/bondhu`; `RequireCIPRBOrg` → `/ciprb`, `/atlas`, `/baseline`; `RequireNotManager` → `/`,
`/reports`, `/tracker`, `/training`; `RequireRecordListAccess` → `/records`, `/infographics`
(blocks field_staff/focal/ciprb_baseline); `RequireTargetConfigAccess` → `/open-questions`;
`RequireSupervisorOrDeveloper` → `/admin`. Admins and any org_lead bypass the partner `RequireOrg`
gates, which is **how UNFPA reaches each partner page**.

---

## 3. Site navigation map (what UNFPA clicks)

| Route | Page | What it shows | Who sees it |
|---|---|---|---|
| `/` | **Home / Programme Overview** | Cross-partner KPI bento, activity feed, **daily-reporting health flags**, anomalies | Everyone except managers |
| `/phd` | **PHD Dashboard** | PHD hero + project brief, 5 SIDA KPI cards, form grid, 22-row indicator grid, coverage map | PHD org + admins/UNFPA |
| `/bondhu` (`/bandhu`→redirect) | **Bandhu Dashboard** | Bandhu hero, 5 UNFPA KPI cards, 18-indicator grid (Obj 1/2/4), form grid, coverage map | Bandhu org + admins/UNFPA |
| `/ciprb` | **CIPRB Dashboard** | Unified Fistula + MPDSR + Maternal Near-Miss surveillance (see §6) | CIPRB org + admins/UNFPA |
| `/atlas` | **MPDSR Atlas** | CIPRB geographic/atlas view of MPDSR | CIPRB org + admins |
| `/baseline` | **Baseline / Endline** | CIPRB baseline assessment survey surface | CIPRB org + admins |
| `/approvals` | **Manager Approvals** | Pending submission queue (PHD 1-stage, Bandhu 2-stage lanes by role) | Managers / org_lead / admins |
| `/tracker` | **Progress Tracker** (+ **Target Config** tab) | Targets vs actuals; source-form column; target editing | Non-managers; edit gated to org_lead |
| `/records` | **Record drill-down** | Per-indicator contributing records | All except field_staff/focal/ciprb_baseline |
| `/infographics` | **Infographics** | Shareable indicator cards (PNG export) | Same as `/records` |
| `/reports` | **Reporting Hub** | Cross-partner reports | Non-managers |
| `/open-questions` | **Open Questions** | Wednesday open-questions log | developer/supervisor/org_lead |
| `/admin` | **Admin Panel** | User management | developer/supervisor |
| `/profile` | **Profile** | Account & password | Any authenticated user |

**Left rail → KoboToolbox panel** (`Spine.tsx`) gives direct Enketo form links, grouped per partner
and shown only to that partner's org + UNFPA + admins (see each partner's form table for the links).
Legacy `/fistula` and `/mpdsr` both redirect to `/ciprb`; `/admin/targets` redirects to `/tracker`.

---

## 4. PHD — Partners in Health and Development
*Project: integrated SRHR for brothel-based female sex workers (FSWs). Funded by UNFPA | Sida.
9 wellness centres across 9 districts; target 44 GBV Corners. Dashboard `/phd`.*

### 4.1 Kobo forms (what field staff fill)

| # | Form | id_string / Enketo | Purpose | Approval |
|---|---|---|---|---|
| 1 | **PHD 1 — FSW Registration** | `phd_registration_v1` · uid `aGWfLrP2yNXqnAiBKuvVgv` · ee.../x/NesXOMsL | Master/Mother list — creates one permanent FSW client per unique ID (`{centre-digit}-{4 digits}`, e.g. `1-0001`). Every Service Log autofills from it (`phd_clients.csv`). | **Auto-approved** (source of truth) |
| 2 | **PHD 2 — Service Log (merged)** | `phd_service_log_v1` · uid `aDv2CZapM2eSqijKr2WZKc` · ee.../x/o7GhleIk | One daily form; a `record_type` selector opens 9 sections: **clinic, htc, counselling, referral, group_edu, event, material, gbv_corner, stock**. | PENDING → **PHD manager** (single stage) |
| — | **No Reporting Today** (shared) | `no_report_v1` · ee.../x/3Ke0ktqc | Nil/zero-day return so a centre isn't flagged "silent". | Single stage |

> *Legacy `phd_patient_services_v1` / `phd_activity_ops_v1` (the old 3-form split) are **decommissioned** — superseded by the merged Service Log. They still appear as the "Source Form" labels in Target Config (a stale FK — see §7).*

### 4.2 What comes from where — PHD dashboard

| Where on the site | Source form | API endpoint | Backing model / logic |
|---|---|---|---|
| `/phd` → **5 SIDA KPI cards** (chip "PHD 1 + PHD 2") | PHD 2 Service Log (+ registry) | `GET /api/indicators/progress/?org=PHD` | `indicators/phd.py` over `programs.*` (APPROVED only): **① FSWs reached**=SL1 (`ClinicVisit`), **② Wellness centres**=SL8 (`ServiceCenter`, *no form*), **③ Outreach sessions**=SL4 (`GroupEducationSession`), **④ Providers capacitated**=SL10–13 (`TrainingEvent`), **⑤ GBV corners**=SL16 (`GBVCornerRecord`) |
| `/phd` → **M&E indicator grid** (22 SL rows) + cumulative tile | PHD 2 (per `KoboFormMapping`) | `GET /api/indicators/progress/?org=PHD` | `IndicatorTarget` (22 rows) joined to `indicators/phd.py` compute fns over `ClinicVisit, HIVSTITestResult, Referral, GroupEducationSession, TrainingEvent, StockEntry, IECMaterial, GBVCornerRecord, ServiceCenter` |
| `/phd` → **Form grid** (per-form counts) | PHD 1 + PHD 2 | `GET /api/dashboard/programs-summary/?partner=PHD` | `count_programs` over `ORG_FORM_TYPES['PHD']` (9 models), APPROVED, this month |
| `/phd` → **Hero coverage map** (chip "Validation workshop (config)") | *Not a Kobo form* | — (static) | `ServiceCenter` geography (seeded) |
| `/phd` → **Hero lede** ("N centres", "N submissions, ±% MoM") | registry + all PHD forms | `GET /api/dashboard/centres/` + `/programs-summary/` | `ServiceCenter` count + `count_programs` |
| **Home** → PHD daily-reporting health flag | nil + any PHD activity | `GET /api/dashboard/health-flags/` | `ServiceCenter` + `NilReport` + daily activity over `programs.*` |
| **Spine** → Approvals badge | all pending | `GET /api/dashboard/kpis/` | `KoboSubmission` PENDING + every `programs.*` PENDING |

> The **Centres district table is hidden for PHD** — it reads the legacy `KoboSubmission` table, but PHD's live data flows through `programs.*` models, so it has nothing to show (see §7).

### 4.3 PHD data flow (end to end)

1. **Register:** MA opens PHD 1, picks her wellness centre + name, enters a unique `id_no`
   (`{centre digit}-{4 digits}`). Kobo enforces the prefix + "not already registered" via
   `phd_clients.csv`. → `/webhook/programs/form/phd_registration_v1/` →
   `handle_phd_registration` → `programs.Client` (org=PHD, FSW, **APPROVED**).
2. **CSV sync:** saving a Client rebuilds `phd_clients.csv` and pushes it to both PHD forms →
   the new FSW is auto-fillable by ID everywhere.
3. **Serve:** MA opens PHD 2, picks `record_type`, types the client ID → name/age autofill →
   enters service data. → `handle_phd_service_log` dispatches to `ClinicVisit` / `HIVSTITestResult` /
   `Referral` / `GroupEducationSession` / `TrainingEvent` / `IECMaterial` / `GBVCornerRecord` /
   `StockEntry` (counselling is logged to raw payload only). Rows land **PENDING**.
4. **Approve:** a PHD manager approves on `/approvals` → **APPROVED** (single stage); cached
   indicator achievements are invalidated.
5. **Visible:** `/phd` cards + indicator grid count **APPROVED** rows only.

---

## 5. Bandhu — Key Population SRHR, HIV & GBV Response
*UNFPA-funded. 8 Drop-in Centres + 1 Dhaka KP clinic. Dashboard `/bondhu`. **Two-stage approval
(Bandhu manager → UNFPA).** 18 indicators across Objectives 1, 2, 4 (no Obj 3).*

### 5.1 Kobo forms

| # | Form | id_string / Enketo | Purpose | Approval |
|---|---|---|---|---|
| 0 | **Bandhu 0 — Mother List** | `bandhu_mother_list_v1` · ee.../x/VO1m2jh1 | Beneficiary master list (every service form autofills from `bandhu_clients.csv`). | **Auto-approved** |
| 1 | **Bandhu 1 — Service Log** | `bandhu_service_log_v1` · ee.../x/DMOqdJFx | `record_type` opens: wellness_logbook (F-01), patient_record (F-05), htc (F-06), gbv (F-02), mh_counseling (F-03), counseling_daily, referral, hiv_identified (F-08). | **Two-stage** |
| 2 | **Bandhu 2 — Activity & Operations** | `bandhu_activity_ops_v1` · ee.../x/WoHgXucH | `record_type` opens: outreach (F-04), mobile_camp (F-10), attendance (F-11), event_report (F-12), stock (F-13), kp_clinic_info (F-07), wellness_center_info (F-09), ebillboard (F-14). | **Two-stage** |
| — | **No Reporting Today** | `no_report_v1` · ee.../x/3Ke0ktqc | Nil return. | **Two-stage** (Bandhu) |

### 5.2 What comes from where — Bandhu dashboard

| Where on the site | Source form (chip) | API endpoint | Backing model / logic |
|---|---|---|---|
| `/bondhu` → **5 UNFPA KPI cards** (chip "Bandhu 0/1/2") | F-05/F-06/F-02/F-12 | `GET /api/indicators/progress/?org=Bandhu` | `indicators/bandhu.py` (APPROVED only): **① KP served**=1.1 (`ClinicVisit`∪`HIVSTITestResult`), **② HIV testing**=1.5b (`HIVSTITestResult`), **③ GBV survivors**=1.2 (`GBVCase`), **④ Drop-in centres** ring=1.8 (`ServiceCenter` DIC), **⑤ Providers trained**=2.1+2.2+2.5 (`TrainingEvent`) |
| `/bondhu` → **18-indicator grid** (Obj 1/2/4) + cumulative tile | per-indicator (see note) | `GET /api/indicators/progress/?org=Bandhu` | `IndicatorTarget` (18 rows) + `indicators/bandhu.py` over `ClinicVisit, HIVSTITestResult, GBVCase, IndividualCounselling, OutreachSession, GroupEducationSession, Referral, MobileHealthCamp, TrainingEvent, CoordMeeting, IECMaterial, ServiceCenter` |
| `/bondhu` → **Form grid** (chip "Bandhu F-01…F-14") | F-04…F-14 family | `GET /api/dashboard/programs-summary/?partner=Bandhu` | `count_programs` over `ORG_FORM_TYPES['Bandhu']` (10 models) — *labelled by model, not raw F-codes* |
| `/bondhu` → **Coverage map** (chip "Validation workshop (config)") | *config* | — | `ServiceCenter` (8 DIC + 1 KP clinic) |
| **Spine** → Approvals badge | pending Bandhu rows | `GET /api/dashboard/kpis/` | `KoboSubmission` + `programs.*` **PENDING** (note: excludes MANAGER_APPROVED — see §7) |

> Per-indicator backing (grid): 1.3 `IndividualCounselling`; 1.4a `OutreachSession`+`GroupEducationSession`; 1.7 `Referral`; 1.9 `MobileHealthCamp`; 2.3/2.4/2.6 `CoordMeeting`; 4.1/4.2 `IECMaterial`(+outreach/condoms). The Bandhu **Centres district table is hidden** (legacy `KoboSubmission`, empty — same as PHD).

### 5.3 Bandhu data flow

Field → Kobo (Mother List / Service Log / Activity-Ops) → `/webhook/programs/` → `bandhu_handlers.py`:
- **Mother List** → `programs.Client` (**auto-approved**).
- **Service Log:** F-05→`ClinicVisit`, F-06→`HIVSTITestResult`, F-02→`GBVCase`, F-03/daily→`IndividualCounselling`, referral/F-08→`Referral`. F-01 → **no DB write**.
- **Activity-Ops:** F-04→`OutreachSession`, F-10→`MobileHealthCamp`, F-12→`TrainingEvent` *or* `CoordMeeting` (by event kind), F-14→`IECMaterial`. F-07/F-09 → **update** the centre in place. F-11/F-13 → **no DB write**.
- New rows land **PENDING** → **Bandhu manager** approves → **MANAGER_APPROVED** → **UNFPA** approves → **APPROVED**. Only then do they count on `/bondhu`. (Manager reject → back to field; UNFPA reject → back to manager.)

---

## 6. CIPRB — Centre for Injury Prevention and Research (monitoring-only)
*One unified dashboard `/ciprb` composing three surveillance programmes: **Fistula, MPDSR, Maternal
Near-Miss**. No approval queue — webhook-saved data is visible immediately. Donor pills (All / GAC / SIDA)
filter every chart by district.*

### 6.1 The 10 CIPRB Kobo forms

| # | Form | id_string · uid | → Model |
|---|---|---|---|
| 1 | **Fistula Question Bank** (5-stage case register) | `ciprb_fistula_questions_v1` · `aH86Euq2AeJ8S9VYdry4PC` | `CIPRBFistulaCase` |
| 2 | **MPDSR 01 — Community Maternal Death** | `ciprb_mpdsr_community_maternal_v1` · `apvPk7qq94nry2aW3z7y4H` | `MPDSRCase` (f1) |
| 3 | **MPDSR 02 — Community Neonatal Death** | `ciprb_mpdsr_community_neonatal_v1` · `awQXeYhuLoLrM38fwSrF8y` | `MPDSRCase` (f2) |
| 4 | **MPDSR 04 — Facility Maternal Death** | `ciprb_mpdsr_facility_maternal_v1` · `aVQbxhGnDHNCe6AazSJByM` | `MPDSRCase` (f4) |
| 5 | **MPDSR 05 — Facility Neonatal Death** | `ciprb_mpdsr_facility_neonatal_v1` · `a6pg47mTt8E56igHnK8SSD` | `MPDSRCase` (f5) |
| 6 | **Social Autopsy** (maternal, Three-Delays) | `ciprb_social_autopsy_v1` · `a6vQiCJ3tz4MRxKqdMHCbA` | `MPDSRCase` (sa_md) |
| 7 | **Death Notification Slip 01** | `ciprb_notification_slip_01_v1` · `aSnEgQT6DUooVanZXubhAF` | `MPDSRDeathNotification` (01) |
| 8 | **Death Notification Slip 02** | `ciprb_notification_slip_02_v1` · `aaCnfRHHgkukkhDgXwUnXX` | `MPDSRDeathNotification` (02) |
| 9 | **Maternal Near-Miss** (WHO MNM audit) | `ciprb_near_miss_v1` · `aTzdRTvhZ8yUQCGhA8UG5R` | `MaternalNearMissCase` |
| 10 | **MPDSR Response Plan** (action tracker) | `ciprb_mpdsr_response_plan_v1` · `auFCf7bfBDtrP6xeW5F2KJ` | `MPDSRActionPlanSummary` *(via the `/webhook/kobo/` dispatcher, not the programs handler)* |

### 6.2 What comes from where — `/ciprb`

**Fistula block**

| Section | Source form | Endpoint | Model |
|---|---|---|---|
| "At a glance" KPI band (Suspected/Diagnosed/Referred/Surgery/Rehab) | CIPRB 1 | `GET /api/fistula/aggregates/` (`.pipeline`) | `CIPRBFistulaCase` |
| Campaign reach + Patient funnel | CIPRB 1 | `/api/fistula/aggregates/` (`.campaign_reach`, `.pipeline`) | `CIPRBFistulaCase` |
| **Anatomical type — VVF/RVF bars** | CIPRB 1 | `/api/fistula/aggregates/` (`.genital_fistula_type`) | `CIPRBFistulaCase` |
| 17 Major Indicators grid | CIPRB 1 | `/api/fistula/aggregates/` (17 keys) | `CIPRBFistulaCase` |
| Surgical Outcome tiles | chip says CIPRB 1, **reads legacy** | `/api/fistula/corner-cases/` | `FistulaCornerCase` ⚠️ (see §7) |
| Diagnosis Pie (cause) | chip says CIPRB 1, **reads legacy** | `/api/fistula/corner-cases/` | `FistulaCornerCase` ⚠️ |
| Fistula registers (Corner / Campaign tabs) | in-app CRUD (legacy) | `/api/fistula/corner-cases/`, `/campaign-visits/` | `FistulaCornerCase`, `FistulaCampaignVisit` |

**MPDSR block** (all via `GET /api/mpdsr/aggregates/` + `GET /api/mpdsr/cases/`, model `MPDSRCase` unless noted)

| Section | Source forms |
|---|---|
| Notify-vs-Review (rates, review tiles, notified-vs-reviewed) | CIPRB 2/3/4/5/6 + Excel denominators (chip understates as "CIPRB 2 + CIPRB 3") |
| Reporting rate per district | CIPRB 2/3 (reported) + Excel (`MPDSRDistrictDenominator`) |
| Cause breakdown (community vs facility donuts) | CIPRB 2 + CIPRB 4 |
| Facility deep-dive (admission→death, review progress) | CIPRB 4 |
| Neonatal deaths | CIPRB 3 + CIPRB 5 |
| Death notifications (kind/level/district) | CIPRB 7 + CIPRB 8 (`MPDSRDeathNotification`) |
| Social Autopsy | CIPRB 6 |
| 11 MPDSR major indicators | CIPRB 2 + CIPRB 4 |
| **Response Plan tracker** | CIPRB 10 (`MPDSRActionPlanSummary`) |
| Raw cases table + audit drawer | CIPRB 2/3/4/5/6 |

**Maternal Near-Miss panel** — CIPRB 9 → `GET /api/mpdsr/mnm/aggregates/` → `MaternalNearMissCase`.
**Coverage map / district map** — config only ("CIPRB M&E Framework" chip), no live endpoint.

### 6.3 CIPRB data flow

Field worker → Kobo (one of 10 forms) → `/webhook/programs/`. **9 forms** route via `ciprb_handlers.py`
(`Fistula→CIPRBFistulaCase`; the four MPDSR + Social Autopsy → `MPDSRCase`; the two slips →
`MPDSRDeathNotification`; Near-Miss → `MaternalNearMissCase`). **Form 10 (Response Plan)** takes a
separate path through `/webhook/kobo/` → `MPDSRActionPlanSummary`. **No approval step** — data is
dashboard-visible on save. The only review action is advancing an MPDSR case's **status** (Reported →
… → Closed) via `PATCH /api/mpdsr/cases/`, which appends an audit-trail entry (editorial, not a gate).
Endpoint access is gated to CIPRB org + UNFPA + admins (`CanAccessMPDSR` / `CanAccessFistulaCases`).

---

## 7. Caveats that affect how you read the numbers
*(Surfaced during the verification pass — none are crashes; they're labelling/data-source nuances UNFPA should know.)*

> **Update — 2026-06-17:** Items **1, 2, 4 (Bandhu), and 5** below have since been **fixed and deployed**: the two fistula visuals now read the live `CIPRBFistulaCase`; the MPDSR section chips now read "CIPRB MPDSR forms + Excel denominators"; the Bandhu form-grid chip now reads "Bandhu 1 + Bandhu 2"; and the PHD indicator "Source Form" now points to the live merged "PHD 2 — Service Log" (migration `indicators.0016`). Items **3, 6, 7** remain as described below. Each fixed item is tagged ✅ inline.

1. ✅ **[FIXED 2026-06-17] CIPRB Fistula — two of five visuals were legacy-backed.** The **Surgical Outcome tiles** and the
   **Diagnosis (cause) Pie** carry a "CIPRB 1" chip but actually read the **legacy `FistulaCornerCase`**
   table (`/fistula/corner-cases/`), *not* the live CIPRB 1 submissions. The reach/funnel, the new
   **VVF/RVF bars**, and the **17 indicators** correctly read the live `CIPRBFistulaCase`. Treat the live
   surgery/cause figures as the indicators grid (#14, #17), not those two visuals, until they're re-pointed.
2. ✅ **[FIXED 2026-06-17] CIPRB MPDSR chip understated sources.** "CIPRB 2 + CIPRB 3" on the Notify-vs-Review and
   reporting-rate sections also includes CIPRB 4/5/6 and **Excel-ingested denominators** (project death
   estimates, facility counts).
3. **PHD/Bandhu "Centres" table & `partner-kpis` read the legacy `KoboSubmission` table**, which is empty
   for both partners (their live data is in `programs.*`). So that district table never renders and those
   legacy KPIs read ~0 — **the trustworthy numbers are the headline cards + indicator grid** (from
   `/indicators/progress/`).
4. ✅ **[Bandhu FIXED 2026-06-17] Form-grid chips were loose labels** — the counts come from the program
   **models**, not the raw Kobo registers. Bandhu's chip now reads "Bandhu 1 + Bandhu 2"; the PHD
   "KoboSubmissions" chip sits on the Centres table, which never renders for PHD (legacy table is empty).
5. ✅ **[FIXED 2026-06-17] PHD Target Config "Source Form" column** previously named the decommissioned
   `PHD-2 — Patient Services` / `PHD-3 — Activity & Operations`; migration `indicators.0016` re-points
   every PHD SL indicator to the live merged `PHD 2 — Service Log` and retires the dead mappings.
6. **Approvals badge counts only `PENDING`** — it does **not** add Bandhu `MANAGER_APPROVED` items, so it
   under-counts the **UNFPA stage-2 queue**. The full UNFPA review lane is correct inside `/approvals` itself.
7. Bandhu **F-01 / F-11 / F-13** and PHD **counselling** are collected but **not stored in a model** (they
   live only in KoboToolbox / raw payload); their volume is reflected indirectly via other forms.

---

*Generated from a verified code trace on 2026-06-17. The navigation sub-trace was cut short by an
account session limit; its content here is reconstructed from each partner's verified page/access map
and the `App.tsx` route guards.*
