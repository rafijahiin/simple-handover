# SIMPLE

The Integrated Digital M&E System built for the Centre for Injury Prevention
and Research, Bangladesh, under the UNFPA-funded Reproductive and Child Health
programme.

Field staff submit through KoboToolbox. Kobo pushes each submission to this
system, where it waits for a manager's approval before it counts. The
dashboard reports on it for three organisations: CIPRB, PHD and Bandhu.

---

## To host it

**Follow [`docs/SERVER_SETUP_GUIDE.md`](docs/SERVER_SETUP_GUIDE.md).** It is a
numbered walkthrough from an empty server to field data arriving, with a check
after every step.

Read Step 0 first. The server has to be reachable from the public internet
over HTTPS on a real domain, because KoboToolbox pushes submissions in. A
machine inside an office network, behind the office firewall, will receive
nothing and show no error.

### What you need

| | |
|---|---|
| Server | 2 CPU cores, 2 GB RAM minimum and 4 GB comfortable, 20 GB disk |
| Operating system | Debian 12, or Ubuntu 22.04 or later |
| Domain | A subdomain such as `simple.example.org`, pointing at the server |
| Certificate | Free from Let's Encrypt, set up in the guide |
| Software | Docker Engine 24 or later, and Docker Compose v2. Nothing else |
| Network | Ports 80 and 443 open inbound from anywhere, and outbound HTTPS to KoboToolbox |
| Accounts | A KoboToolbox account that can edit REST Services on the deployed forms |

Everything the application itself needs, Python, Node, Chromium and the system
libraries, is inside the Docker image.

### The short version

```bash
git clone https://github.com/rafijahiin/simple-handover.git simple
cd simple
cp .env.example .env     # then fill it in, see the guide
docker compose up -d --build
```

Then put Nginx and a certificate in front, create the login accounts, and
repoint the KoboToolbox REST Services at the new domain. All four are steps in
the guide.

---

## What this repository contains

The complete application, and no data. There is no database, no dump, no
fixtures and no uploaded files, so a fresh clone gives you a working system
with an empty database. `.env.example` lists every setting the system needs,
all with placeholder values.

---

## The stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 5.2 with Django REST Framework |
| Database | PostgreSQL 17 or later |
| Application server | Gunicorn, behind Nginx |
| Static files | WhiteNoise, inside the application |
| Frontend | React with TypeScript, built by Vite |
| Report rendering | Playwright with headless Chromium |
| Container | Docker, multi-stage |

The React build is served by Django itself, so there is no separate frontend
server and no CORS to configure. The API is under `/api`, and every other path
returns the React application.

### Applications

| App | What it holds |
|---|---|
| `accounts` | Users, the three organisations, role middleware |
| `submissions` | The Kobo webhook, raw submission store, alerts |
| `programs` | PHD and Bandhu service delivery, clients, stock, the Kobo form builders |
| `indicators` | Indicator definitions, targets and the counting logic |
| `mpdsr` | Maternal and perinatal death surveillance, near miss, response plans |
| `fistula` | Fistula case tracking and the campaign tracker |
| `baseline` | The two baseline surveys and the anomaly rule engine |
| `training` | Training events and logs |
| `reports` | Monthly Word, PDF, PowerPoint, one-pager and newsletter output |
| `tracker` | Reporting gap detection, alerts, monthly targets |
| `dashboard` | The aggregation endpoints behind every chart |
| `partners`, `pharmacy` | Partner reference data, prescription records |

---

## Running it locally

For development, rather than on a server.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
export DJANGO_SETTINGS_MODULE=spondon.settings.development
python manage.py migrate
python manage.py seed_users
python manage.py seed_centers
python manage.py runserver
```

The frontend builds separately:

```bash
cd frontend && npm install && npm run build
```

Tests:

```bash
DJANGO_SETTINGS_MODULE=spondon.settings.development python manage.py test
```

---

## Documentation

`docs/handover/` holds the operational documentation.

| File | Read it for |
|---|---|
| `SIMPLE_Handover_8_Server_Setup_Guide.pdf` | Hosting this on your own server. Same content as `docs/SERVER_SETUP_GUIDE.md` |
| `SIMPLE_Handover_1_Operations_Runbook.pdf` | Running and operating the system day to day |
| `SIMPLE_Handover_2_Troubleshooting_Playbook.pdf` | What to do when something breaks |
| `SIMPLE_Handover_3_Indicator_Dictionary.pdf` | What every indicator counts, and from which form |
| `SIMPLE_Handover_6_Dashboard_Manual_Bangla.pdf` | Dashboard manual, Bangla |
| `SIMPLE_Handover_7_Maintainer_FAQ.docx` | Stack map and maintainer questions |
| `Kobo_Manager_Manual_{CIPRB,PHD,Bandhu}.pdf` | Per-organisation Kobo administration |
| `Kobo_User_Manual_Bangla_SIMPLE.pdf` | Field staff manual, Bangla |
| `Bandhu_*.pdf` | Bandhu's guides, form book and wall chart, Bangla |
| `kobo-form-docs/` | Every deployed Kobo form, written out question by question |

`SEMANTICS.md`, at the repository root, records what each term on the CIPRB
dashboard is defined to mean where the data does not settle it by itself. Read
it before changing any counting logic. It has to stay at the root, because a
test asserts the path.

---

## Running this in your own KoboToolbox account

The forms are routed by the form id inside the XLSForm, which survives being
imported into another account, so routing needs no configuration.

Everything this system sends *out* to KoboToolbox does need the asset UID, and
those change when the forms are deployed in a different account: the
`system_ref` write-back, the two lookup CSV exporters and the reconciliation
loop. They all resolve through `programs/kobo_uids.py`, in this order:

1. `KOBO_ASSET_UID_<SLUG>` in the environment, upper-cased.
2. `indicators.KoboFormMapping.kobo_asset_uid` for that slug. This is the
   normal route, and Step 9e of the setup guide is where it gets filled in.
3. The built-in default, which is the account the system was first deployed
   against.

The webhook health check reads `SIMPLE_PUBLIC_URL` for the same reason. Set
it, or the check reports every hook as pointing somewhere else.

`programs/test_kobo_uid_resolution.py` holds this down.
