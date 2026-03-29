# QuickAssist – Claude Code Instructions

## Project Overview

**QuickAssist Northwest** is a Django web application for roadside recovery assistance in Northwest England. It serves three user roles: **Members** (vehicle owners requesting help), **Drivers** (providing recovery services), and **Admins** (managing operations). All pages are server-rendered Django templates — there is no separate API or frontend build system.

---

## Tech Stack

- **Backend:** Django 6.0.3 (Python 3.x)
- **Auth:** Django session authentication (no JWT, no DRF)
- **Frontend:** Django templates, plain HTML/CSS
- **Database:** PostgreSQL (psycopg2-binary)
- **Distance:** Haversine formula implemented in Python (no PostGIS)
- **DVLA:** UK vehicle registration lookup via `requests` library
- **Server:** Gunicorn (production), `runserver` (dev)
- **Containerisation:** Docker + docker-compose

---

## Project Structure

```
roadside_recovery/
├── roadsideassist/          # Django project config (settings, urls, wsgi)
├── usermanagement/          # All active views, models, URLs — the core app
├── recovery/                # Models only (RecoveryRequest, Assignment, JobHistory)
├── services/                # Models only (Service)
├── core/                    # Home page view + static assets
├── templates/               # Global templates (base.html, portal.html, partials/)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

> **Note:** `recovery/views.py` and `services/views.py` are empty. All business logic lives in `usermanagement/views.py`. `recovery/` and `services/` have no `urls.py`.

---

## Database

- **Engine:** `django.db.backends.postgresql`
- **Config:** Read from env vars `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (fallback to `roadside_recovery / postgres / admin / localhost / 5432`)
- **Custom User model:** `usermanagement.User` (set via `AUTH_USER_MODEL`)

### Models

#### `usermanagement` app

| Model | Key Fields |
|---|---|
| `User` | `uuid` (PK), `role` (MEMBER/DRIVER/ADMIN), `email` (unique), `status` (APPROVED/PENDING/REJECTED), `active`, `deleted_at` |
| `UserProfile` | `user` (1:1), `first_name`, `last_name`, `phone`, `address`, `membership_tier` (STANDARD/PREMIUM) |
| `DriverStatus` | `user` (1:1), `status` (AVAILABLE/OFFLINE/IN_PROGRESS), `license_number`, `vehicle_type` (MOBILE_UNIT/TOW_TRUCK/FLATBED), `vehicle_registration`, `qualification` (JSON), `specialization` (JSON list of service IDs) |
| `DriverLocation` | `driver` (FK→User, related_name=`usermanagement_locations`), `latitude`, `longitude`, `is_current` |

#### `recovery` app

| Model | Key Fields |
|---|---|
| `RecoveryRequest` | `member` (FK→User), `service` (FK→Service), `lat/lon`, `address`, `issue_description`, `vehicle_details`, `status` (PENDING/IN-PROGRESS/ASSIGNED/COMPLETED/CANCELLED), `priority` (NORMAL/EMERGENCY/MEDIUM), `place` (MOTORWAY/ROAD/NEAR HOUSE) |
| `Assignment` | `request` (FK→RecoveryRequest), `driver` (FK→DriverStatus), `offer_sent_at`, `driver_response` (ACCEPTED/DECLINED/TIMEOUT), `accepted_at`, `completed_at`, `cancellation_reason`, `assistance_requested_at` |
| `JobHistory` | `request` (1:1), `driver` (FK→DriverStatus), `assignment` (1:1), `start_time`, `end_time`, `completion_time_minutes`, `member_rating`, `driver_notes` |
| `DriverLocation` | Duplicate model (related_name=`recovery_locations`) — views use the usermanagement version |

#### `services` app

| Model | Key Fields |
|---|---|
| `Service` | `name`, `description`, `active`, `estimated_duration`, `price` (CharField) |

---

## Key Business Rules

- **Dispatch algorithm:** Top 3 nearest available drivers offered per batch (`DISPATCH_BATCH_SIZE = 3`). Ranked by: AVAILABLE status → specialisation match → Haversine distance.
- **Offer window:** 60 seconds (`DRIVER_RESPONSE_TIMEOUT_SECONDS = 60`). No response = TIMEOUT. Expired offers rotate to next batch.
- **Offer rotation:** `_rotate_expired_dispatch_offers()` is called opportunistically on dashboard load — there is no background scheduler.
- **Priority auto-assignment:** `MOTORWAY` → EMERGENCY, others → NORMAL.
- **Request status flow:** `PENDING` → `IN-PROGRESS` → `COMPLETED` (or `CANCELLED`). `ASSIGNED` status also used on manual admin assignment.
- **Driver status values:** `AVAILABLE`, `OFFLINE`, `IN_PROGRESS` (not ON_JOB/BREAK).
- **Soft deletes:** Users: set `active=False` + `deleted_at`. Services: set `active=False`. Never hard-delete.
- **Specialisation matching:** `DriverStatus.specialization` is a JSON list of service IDs or names. Both formats are supported.
- **Driver location eligibility:** Only drivers with an `is_current=True` DriverLocation record are dispatched.
- **DVLA lookup:** `lookup_vehicle` view calls UK DVLA API — requires `DVLA_API_KEY` in settings.

---

## URL Reference (`usermanagement/urls.py`)

### Page routes

| URL | View | Role |
|---|---|---|
| `register/` | register_view | Public |
| `login/` | login_view | Public |
| `dashboard/` | dashboard | All (role-branched) |
| `dashboard/members/` | members | Admin |
| `dashboard/recovery-requests/` | admin_recovery_requests | Admin |
| `dashboard/services/` | admin_services | Admin |
| `dashboard/analytics/` | admin_analytics | Admin |
| `dashboard/driver-requests/` | driver_requests | Admin |
| `dashboard/handle-request/<uuid>/` | admin_handle_request | Admin |
| `dashboard/recovery-requests/<id>/assign/` | assign_recovery_request | Admin |
| `dashboard/recovery-requests/<id>/decline/` | decline_recovery_request | Admin |
| `submit-request/` | submit_request | Member |
| `cancel-request/<id>/` | cancel_request | Member |
| `lookup-vehicle/` | lookup_vehicle | Member |

### API / JSON routes

| URL | View | Consumer |
|---|---|---|
| `api/driver-locations/` | get_driver_locations | Admin (map) |
| `api/member-requests-status/` | member_requests_status | Member (polling) |
| `api/member-request-driver-location/<id>/` | member_request_driver_location | Member (tracking) |
| `api/update-location/` | update_driver_location | Driver |
| `api/update-driver-status/` | update_driver_status | Driver |
| `api/driver-assignment-snapshot/` | driver_assignment_snapshot | Driver (polling) |
| `api/accept-driver-assignment/` | accept_driver_assignment | Driver |
| `api/complete-driver-assignment/` | complete_driver_assignment | Driver |
| `api/cancel-driver-assignment/` | cancel_driver_assignment | Driver |
| `api/request-driver-assistance/` | request_driver_assistance | Driver |

---

## Authentication & Permissions

- **Session-based auth** (Django's built-in `login` / `logout`). No JWT, no DRF.
- Role check pattern used throughout views: `request.user.role == 'ADMIN'`
- `@login_required` decorator used on all protected views.
- User must have `status == 'APPROVED'` to access most functionality.

---

## Development Conventions

### Code Style
- Follow Django conventions and PEP 8
- Use `settings.AUTH_USER_MODEL` (not direct User import) for all FK references to the user model
- Use `auto_now_add=True` for `created_at`, `auto_now=True` for `updated_at`
- Soft-delete only — never hard-delete User or Service records

### Models
- Driver FK references should target `usermanagement.DriverStatus`, not User directly
- New models go in the relevant app (`recovery/` for request-related, `usermanagement/` for user-related)

### Views
- All new views go in `usermanagement/views.py` unless creating a separate app with its own urls.py
- JSON endpoints return `JsonResponse`; page views return `render()`
- Role guard pattern: check `request.user.role` and return 403 / redirect for wrong role

### Migrations
- Run `python manage.py makemigrations && python manage.py migrate` after every model change
- Never edit migration files manually

### Templates
- Global templates: `templates/` (base.html, portal.html, partials/)
- App-specific templates: `<app>/templates/<app>/`

---

## Running the Project

### With Docker (recommended)
```bash
docker compose up --build
# App available at http://localhost:8000
# Migrations run automatically on startup

# Create superuser
docker compose exec web python manage.py createsuperuser
```

### Without Docker
```bash
# Windows — activate virtual environment
venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

---

## Project Timeline Context

This is a **12-week solo academic project** (~180 hours total).

| Release | Week | Scope |
|---|---|---|
| Alpha | 5 | Foundation, auth, services, requests, admin manual assignment |
| Beta | 8 | Automated driver matching, offer system, job workflow, tracking |
| Gamma | 11 | CR-001 (Advanced Search), bug fixes |
| Final | 12 | Demo, documentation |

**Approved change requests:**
- CR-001: Advanced Search (Week 9, 19 hours) ✅

**Rejected change requests:**
- CR-004: User Review & Rating system ❌ (insufficient buffer capacity)

---

## Important Notes for Claude Code

1. **Do not add features outside the approved scope** — fixed 12-week timeline.
2. **No DRF, no JWT** — this project uses Django sessions and server-rendered templates only.
3. **No background task runner** — offer rotation is triggered opportunistically in views, not by Celery/cron.
4. **No PostGIS** — distance calculations use the Python `_haversine_km()` helper in `usermanagement/views.py`.
5. **Duplicate DriverLocation model** — `usermanagement.DriverLocation` and `recovery.DriverLocation` both exist. All views use the `usermanagement` one. Do not add logic to the `recovery` version.
6. **requirements.txt must stay ASCII/UTF-8** — the original file was UTF-16 encoded and broke Docker builds.
7. When adding URLs, register them in `usermanagement/urls.py` unless creating a new app with its own routing.
