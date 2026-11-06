# Forms by Field-Staff Role

Map of which Kobo form belongs to which worker type. Use this when a focal asks "which of my staff need which links."

## PHD — clinical site staff

| Role | Forms |
|---|---|
| Medical Assistant / Paramedic | KF-01 Client Reg, KF-02 Clinic Visit, KF-04 HTC, KF-05/06 MH Screen, KF-13 ADR, KF-ANC Antenatal |
| Lab Technician | KF-03 HIV/STI Test, KF-16 Autoclave Log |
| Counsellor | KF-04 HTC Counselling, KF-05/06 MH Screen, KF-09 Individual Counselling |
| Field Worker / Outreach | KF-08 Outreach, KF-10 Group Education, KF-12 Hygiene Kit, Referral, GBV Case |

## Bandhu — community outreach staff

| Role | Forms |
|---|---|
| Field Worker | KF-08 Outreach, KF-09 Counselling, KF-10 Group Education |
| Peer Educator | KF-12 Hygiene Kit, Referral |
| Outreach Coordinator | KF-08, KF-09, KF-10, KF-18 Mobile Camp, KF-19 Coord Meeting |

## CIPRB — programme operations (rare submitters)

| Role | Forms |
|---|---|
| Programme Officer | KF-19 Coord Meeting, KF-20 Training, MPDSR, Fistula Campaign, Fistula Corner |
| Baseline Surveyor | Baseline / Endline |

## Quick lookup — by form

| Form | Slug | Enketo URL | Typical submitter |
|---|---|---|---|
| MPDSR | spondon_mpdsr_v1 | https://ee.kobotoolbox.org/x/ZOBX0pKd | Hospital focal |
| Fistula Campaign (legacy) | spondon_fistula_campaign_v0 | https://ee.kobotoolbox.org/x/MHkEKfzl | Campaign visit team — legacy entry retained |
| Fistula Campaign Visit (house screening) | spondon_fistula_campaign_v1 | https://ee.kobotoolbox.org/x/7bMvJPU4 | CIPRB campaign team |
| Fistula Corner Case | spondon_fistula_corner_v1 | https://ee.kobotoolbox.org/x/2EemD80H | CIPRB district hospital clinical staff |
| Baseline / Endline | spondon_baseline_v1 | https://ee.kobotoolbox.org/x/MTvoZ3Hz | Survey enumerator |
| KF-01 Client Registration | spondon_kf01_client_v1 | https://ee.kobotoolbox.org/x/J1WaMhw9 | Clinic reception |
| KF-02 Clinic Visit | spondon_kf02_visit_v1 | https://ee.kobotoolbox.org/x/TAxdHQQu | Medical assistant |
| KF-03 HIV/STI Test | spondon_kf03_hivsti_v1 | https://ee.kobotoolbox.org/x/svhvZM4N | Lab technician |
| KF-04 HTC Counselling | spondon_kf04_htc_v1 | https://ee.kobotoolbox.org/x/ut3WZTdw | Counsellor |
| KF-05/06 MH Screening | spondon_kf0506_mh_v1 | https://ee.kobotoolbox.org/x/hVfZFf66 | Counsellor |
| KF-08 Outreach | spondon_kf08_outreach_v1 | https://ee.kobotoolbox.org/x/mL50QRl8 | Field worker |
| KF-09 Counselling | spondon_kf09_counsel_v1 | https://ee.kobotoolbox.org/x/5X3kRnOV | Counsellor / peer ed |
| KF-10 Group Education | spondon_kf10_group_v1 | https://ee.kobotoolbox.org/x/VZ1iYrTd | Field worker |
| KF-12 Hygiene Kit | spondon_kf12_hygiene_v1 | https://ee.kobotoolbox.org/x/txflM4ZZ | Field worker |
| KF-13 ADR Record | spondon_kf13_adr_v1 | https://ee.kobotoolbox.org/x/33qxf43w | Clinical |
| KF-16 Autoclave Log | spondon_kf16_autoclave_v1 | https://ee.kobotoolbox.org/x/bdciLLr4 | Lab |
| KF-ANC Antenatal | spondon_kfanc_v1 | https://ee.kobotoolbox.org/x/DKpvTw58 | Medical assistant |
| KF-18 Mobile Camp | spondon_kf18_camp_v1 | https://ee.kobotoolbox.org/x/Bc7XiGmm | Outreach coord |
| KF-19 Coord Meeting | spondon_kf19_meeting_v1 | https://ee.kobotoolbox.org/x/BW115Ila | Programme officer |
| KF-20 Training | spondon_kf20_training_v1 | https://ee.kobotoolbox.org/x/bRmo6yVq | Programme officer |
| KF-MPDSR Response Plan | spondon_mpdsr_response_plan_v1 | https://ee.kobotoolbox.org/x/7kAJGedj | CIPRB district focal (per Animesh) |
| KF-Fistula Staged (Auto-ID, 5 stages) | spondon_fistula_staged_v1 | https://ee.kobotoolbox.org/x/mc06MRIn | CIPRB clinical staff — Animesh's staged-entry design |
| Referral | spondon_referral_v1 | https://ee.kobotoolbox.org/x/VF7qdmTN | Any |
| GBV Case | spondon_gbv_v1 | https://ee.kobotoolbox.org/x/v9gd1IPa | Trained counsellor only |

## Notes

- **GBV form** is sensitive (encrypted PII). Restrict the link to trained counsellors only — don't put it in the general broadcast group.
- **MPDSR + Fistula Corner** are not for general field staff. CIPRB clinical / hospital focal only.
- **KF-20 Training URL** was previously suspected as a duplicate of KF-02; confirmed via Kobo API that KF-20's correct URL is `https://ee.kobotoolbox.org/x/bRmo6yVq` and the actual mismatch was KF-02 (now fixed).
- If a worker submits the wrong form, manager rejects with reason "wrong form — please use [correct one]" and the system tells them to resubmit.
