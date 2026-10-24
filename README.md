# ProcureFlow

A multi-company procurement REST API built with Django REST Framework and PostgreSQL. ProcureFlow follows a purchase from an employee's request through management approval, supplier quotations, purchase ordering, and goods receiving.

The backend enforces company boundaries, role permissions, workflow transitions, and quantity and monetary checks. PostgreSQL transactions and row locks protect decisions and receiving from concurrent requests. Audit events commit with the business change.

## Features

- JWT login with short-lived access tokens, refresh rotation and blacklisting, password-change revocation, and authentication throttling.
- Company-scoped supplier, employee, request, RFQ, quotation, and order access.
- Employee requests with nested items and estimated totals; manager approval or rejection with comments.
- RFQs for approved requests, active supplier invitations, deadlines, quote comparison, and one selected quote per RFQ.
- Orders that match all request items, quantities, and the selected quotation total.
- Partial and full receiving with duplicate-item and over-receiving checks.
- Private quotation attachments (PDF, PNG, JPEG; up to 5 MiB), downloaded through the authenticated API.
- Idempotent in-application notifications and hourly RFQ reminders using Celery, Redis, and a database-backed scheduler.
- OpenAPI schema, Swagger UI, health endpoints, production settings, HTTPS proxy configuration, and CI checks.

Notifications are database records. This project does not implement email delivery, supplier self-service accounts, inventory valuation, tax calculations, or currency conversion.

## Architecture

| Component | Responsibility |
| --- | --- |
| `apps/accounts` | Custom user, JWT authentication, company user directory, RBAC |
| `apps/companies` | Company identity |
| `apps/suppliers` | Company supplier directory |
| `apps/procurement` | Requests, approval, RFQs, quotes, orders, and receiving |
| `apps/audit` | Transactional audit records |
| `apps/notifications` | Notification tasks and RFQ reminders |
| `apps/core` | Health checks and platform admin access |
| `config/settings/{dev,test,prod}.py` | Environment-specific configuration |
| `tests/` | API, security, integrity, rollback, and concurrency tests |
| `deploy/nginx.conf` | Production TLS termination and static files |

Python 3.11, Django 5.2, DRF, PostgreSQL 17, Redis 7, Celery, Simple JWT, drf-spectacular, pytest, and Gunicorn are used. Runtime dependencies are pinned in `requirements/base.txt`; development and production additions are separate.

### Workflow

```text
Purchase request: DRAFT -> PENDING_APPROVAL -> APPROVED or REJECTED
RFQ:             DRAFT -> SENT -> CLOSED (when a quote is selected)
Quotation:       SUBMITTED -> SELECTED or REJECTED
Purchase order:  OPEN -> PARTIALLY_RECEIVED -> COMPLETED
```

Approval and rejection are final. A manager cannot approve or reject their own request. Quotes can be submitted only before the deadline on sent RFQs; selection can happen before or after the deadline. A selected quote closes its RFQ. Purchase orders require that closed RFQ and an approved request. Receiving is cumulative, and cannot exceed ordered quantities.

Mutating workflow actions lock the relevant request, RFQ, or order inside a transaction. Database constraints enforce positive quantities and prices, valid statuses, unique supplier quotes, one selected quote, and one order per request. Order items may be supplied in any order but must match all original request items.

### Access model

| Role | Requests | Suppliers | RFQs / quotations | Orders / receiving |
| --- | --- | --- | --- | --- |
| Employee | Create, view own, submit own | Read company directory | No access | Read company orders |
| Manager | View company requests, approve / reject | Read company directory | No access | Read company orders |
| Procurement officer | View company requests | Manage | Manage | Create orders, receive |
| Company admin | View company requests | Manage | Manage | Create orders, receive |

Only company admins can view and edit the company user directory. That endpoint edits username and email; company assignment and roles are operator-managed. All business access requires a company assignment.

Public registration creates an employee with no company, staff rights, or elevated role. A platform operator must assign the company and role before procurement access is available. Django admin is restricted to active staff superusers and is intended for trusted platform operators. Company admins do not receive Django admin access.

## Local setup (PowerShell)

Prerequisites: Python 3.11, PostgreSQL, and Redis. Use Docker Desktop with a running Linux container engine if you prefer the container setup below.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Put the generated key in `DJANGO_SECRET_KEY` in `.env`. Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` to your local PostgreSQL database. The database and its login must already exist. Redis defaults to `127.0.0.1:6379`. Keep `.env` private.

For a fresh PostgreSQL installation, an operator can create the local role and database with `psql -U postgres`:

```sql
CREATE ROLE procureflow_user WITH LOGIN PASSWORD 'replace-with-a-local-database-password';
CREATE DATABASE procureflow_db OWNER procureflow_user;
-- Local testing only: Django creates and drops a separate test database.
ALTER ROLE procureflow_user CREATEDB;
```

Use a separate restricted database login for production.

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- API: http://127.0.0.1:8000/api/
- Swagger UI: http://127.0.0.1:8000/api/docs/
- OpenAPI: http://127.0.0.1:8000/api/schema/
- Platform admin: http://127.0.0.1:8000/admin/

Sign in to platform admin to create companies and assign company membership and roles to registered users. Platform superusers have no procurement role bypass; assign a role and company when using their API credentials.

For local background processing, run each command in a separate terminal with the same virtual environment and settings:

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
celery -A config worker --loglevel=info --pool=solo
```

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
celery -A config beat --loglevel=info
```

Use the default worker pool on Linux. Run a single Beat instance per database. The scheduler sends RFQ reminders hourly and removes expired JWT blacklist records daily.

### Docker development

Configure `.env` as above, then:

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
docker compose logs -f web celery celery-beat
```

Compose starts PostgreSQL, Redis, a migration job, the API, the worker, and Beat. Application services wait for migrations. Ports 8000, 5432, and 6379 bind to localhost. Stop local PostgreSQL or Redis first if those ports are already occupied. Database and upload data use named volumes.

To run only the local infrastructure for a host Python process:

```powershell
docker compose up -d db redis
```

## API usage

Register and log in:

```powershell
$body = @{username="employee"; email="employee@example.com"; password="choose-a-strong-password"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/register/ -ContentType application/json -Body $body

$login = @{username="employee"; password="choose-a-strong-password"} | ConvertTo-Json
$tokens = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/login/ -ContentType application/json -Body $login
$headers = @{Authorization="Bearer $($tokens.access)"}
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/auth/me/ -Headers $headers
```

Assign the user's company and role using platform admin. Access tokens last five minutes. POST `{"refresh":"..."}` to `/api/auth/refresh/` to rotate the refresh token. Store the returned refresh token and discard the old one; replay is rejected. Account deactivation, deletion, and password changes invalidate authentication.

| Endpoint | Methods / actions |
| --- | --- |
| `/api/auth/register/`, `login/`, `refresh/` | POST |
| `/api/auth/me/` | GET |
| `/api/auth/company-users/` | GET; detail GET / PUT / PATCH |
| `/api/company/` | GET authenticated user's company |
| `/api/suppliers/` | GET / POST; detail GET / PUT / PATCH / DELETE |
| `/api/purchase-requests/` | GET / POST; detail GET |
| `/api/purchase-requests/{id}/submit/` | POST |
| `/api/purchase-requests/{id}/approve/`, `reject/` | POST optional `comment` |
| `/api/rfqs/` | GET / POST; detail GET |
| `/api/rfqs/{id}/send/` | POST |
| `/api/rfqs/{id}/quotes/` | GET quote comparison |
| `/api/rfqs/{id}/quotes/{quote_id}/select/` | POST |
| `/api/quotes/` | GET / POST; detail GET |
| `/api/quotes/{id}/attachment/` | GET authenticated file download |
| `/api/purchase-orders/` | GET / POST; detail GET |
| `/api/purchase-orders/{id}/receive/` | POST |

Send `Authorization: Bearer <access-token>` for protected endpoints. Quote uploads use multipart form data; other writes use JSON. Swagger documents the exact input and output schemas. Foreign-company resources return 404 on detail routes; invalid related IDs return 400 without exposing foreign records.

Generate the schema:

```powershell
python manage.py spectacular --file schema.yml --validate --fail-on-warn
```

## Testing

Tests use real PostgreSQL, including multiple connections for concurrency checks. The local test database user needs `CREATEDB` permission. Redis and a worker are not needed for unit/API tests: `config.settings.test` runs tasks eagerly and uses a faster password hasher only for tests.

If the shell is already configured for development, select test settings explicitly:

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.test"
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pip check
python -m pytest -q
```

`DB_TEST_NAME` optionally selects a dedicated test database name; do not point it at an existing database containing valuable data. Avoid parallel test runs against the same test database.

The suite covers JWT authentication, token replay and account changes, company isolation, RBAC, private files, input validation, state transitions, audit rollback, database constraints, health responses, production settings, and concurrent approval, selection, quote/RFQ/order creation, and receiving.

GitHub Actions runs checks, schema validation, production settings checks, static collection, Compose validation, the test suite with PostgreSQL and Redis, and a production image build. CI configuration is included; inspect the Actions tab for actual remote results.

## Production preparation

Production is a separate stack: `docker-compose.prod.yml`. It uses Gunicorn and nginx with TLS. PostgreSQL, Redis, and the application server have no published ports. nginx serves collected static files and forwards API requests with an overwritten HTTPS header. Uploads are available only through authenticated API downloads.

1. Back up the database and upload volume, and verify restoration. Test the release against a copy of existing data. Migration `procurement.0004` adds constraints: invalid historical quantities, prices, statuses, or multiple selected quotes must be corrected explicitly before migration. The migration does not silently rewrite business data.
2. Copy `.env.production.example` to `.env.production`. Set a new random secret of at least 50 characters, explicit hostnames, HTTPS CSRF origins, strong database credentials, and the service URLs. Production never automatically reads the development `.env`.
3. Supply trusted certificates at `deploy/certs/fullchain.pem` and `deploy/certs/privkey.pem`. Configure certificate renewal and domain DNS. These files are ignored by Git and Docker builds.
4. The example uses `DB_SSLMODE=disable` for the private same-host Compose database only. Use verified TLS for remote PostgreSQL. Keep PostgreSQL and Redis private; authenticate remote Redis connections and use TLS.
5. HTTPS redirect, secure session/CSRF cookies, content-type protection, HSTS, console logging, and persistent database connections are enabled. HSTS covers subdomains and allows preload: ensure all subdomains support HTTPS before publishing.
6. `DJANGO_TRUST_PROXY=true` trusts the proxy's scheme header. Use it only with the private backend network and a proxy which overwrites that header. The included nginx configuration does this.
7. Review dependency and container vulnerability scans, resource limits, backups, monitoring, and certificate renewal before launch.

Preparation and verification commands (run on a staging host first):

```powershell
Copy-Item .env.production.example .env.production
# Edit .env.production and install TLS certificates before starting services.
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps web python manage.py check --deploy --fail-level WARNING
# The following commands start the stack; run only when ready to launch it.
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

The one-shot `init` service migrates and collects static files before application services start. Recreate that job for subsequent releases before restarting web and workers:

```powershell
docker compose --env-file .env.production -f docker-compose.prod.yml stop web celery celery-beat proxy
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm init
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --force-recreate web celery celery-beat proxy
```

Run only one scheduler. Reconcile existing database-scheduled tasks before changing the built-in schedule, to avoid duplicate schedules.

Health checks: `/health/live/` tests the API process; `/health/ready/` checks PostgreSQL and the Redis broker and returns 503 when unavailable. Readiness does not prove the worker or scheduler is processing jobs. Monitor worker health, queue depth, scheduler activity, failed tasks, disk space, application errors, and backup jobs separately.

Notifications are created after commit and are idempotent. If publishing to Redis fails, the application logs the failure and creates the order notification locally. Monitor callback/task errors; this is not a general durable messaging outbox. Audit and notification records currently have no public read API; inspect them through trusted operator tooling.

Existing endpoint paths and response shapes are preserved. The attachment field now returns a protected API URL; clients must include a valid bearer token when downloading. After upgrading JWT security settings, users should log in again.

No external deployment is performed by this repository review. See [the technical review](docs/technical-review.md) for the verified results and remaining validation work.
