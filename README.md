# ProcureFlow

ProcureFlow is a REST API for managing procurement workflows within an organization. It brings purchase requests, supplier quotations, purchase orders, and goods receiving into one process, with role-based access and a record of important changes.

The project is built with Django REST Framework and PostgreSQL. It focuses on keeping procurement rules in the backend, separating company data, and making workflow transitions explicit and testable.

## What it covers

- **Purchase requests:** Employees create requests and submit them for approval. Authorized users can approve or reject them.
- **Supplier management:** Maintain supplier records within each company.
- **Requests for quotation (RFQs):** Send RFQs to suppliers, review submitted quotations, and select a quote.
- **Purchase orders:** Create orders from approved requests and selected quotations.
- **Goods receiving:** Record received items and track whether an order is partially or fully received.
- **Access control:** JWT authentication and role-based permissions, with company-scoped access to business data.
- **Notifications:** Background tasks and scheduled reminders for RFQs using Celery and Redis.
- **Audit logging:** Record key procurement actions, including the actor, affected record, and before/after values. Audit writes are part of the same database transaction as the associated change.

## Workflow

```text
Purchase request
    |
    v
Submit for approval
    |
    +---- Rejected
    |
    v
Approved
    |
    v
Request for quotation
    |
    v
Supplier quotations
    |
    v
Select quotation
    |
    v
Purchase order
    |
    v
Receive goods
    |
    +---- Partially received
    |
    v
Completed
```

Business rules are enforced on the server rather than relying on clients to send valid status changes.

## Tech stack

| Area | Technology |
| --- | --- |
| API | Python 3.11, Django, Django REST Framework |
| Database | PostgreSQL |
| Authentication | JWT (Simple JWT) |
| Background jobs | Celery, Redis, django-celery-beat |
| API documentation | drf-spectacular, OpenAPI, Swagger UI |
| Testing | pytest, pytest-django |
| Container setup | Docker, Docker Compose |
| Continuous integration | GitHub Actions |

## Project structure

```text
apps/
  accounts/        # Users and authentication-related logic
  companies/       # Company data
  suppliers/       # Supplier management
  procurement/     # Requests, RFQs, quotations, orders and receiving
  notifications/   # Background notifications and reminders
  audit/           # Audit records and logging service
  core/            # Shared application code
config/            # Django settings, URL routing and Celery setup
tests/             # Automated tests
Dockerfile
docker-compose.yml
requirements.txt
```

## Running locally

You will need Python 3.11, PostgreSQL, and Redis. The commands below assume PowerShell on Windows; adjust the virtual environment activation command for your shell.

**1. Install dependencies**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**2. Configure environment variables**

Create a `.env` file in the project root. Use your own values and do not commit this file.

```dotenv
DJANGO_SECRET_KEY=replace-with-a-random-secret
DB_NAME=procureflow_db
DB_USER=procureflow_user
DB_PASSWORD=replace-with-your-database-password
DB_HOST=127.0.0.1
DB_PORT=5432
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

Create the PostgreSQL database and user to match these settings, and make sure Redis is running.

**3. Apply migrations and start the API**

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py migrate
python manage.py runserver
```

The API will be available at `http://127.0.0.1:8000/`.

**4. Run background jobs (optional)**

Start a Celery worker and scheduler in separate terminals with the same environment configuration:

```powershell
celery -A config worker --loglevel=info --pool=solo
```

```powershell
celery -A config beat --loglevel=info
```

The `solo` worker pool is useful for local Windows development. On Linux, the default worker pool can be used.

## API documentation

With the development server running:

- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`

The schema can also be generated from the command line:

```powershell
python manage.py spectacular --file schema.yml --validate
```

JWT authentication is required for protected endpoints. The Swagger interface is the easiest place to explore the available routes, request bodies, and responses.

## Tests

Run the full test suite with:

```powershell
python -m pytest -q
```

The tests cover procurement behavior and audit logging, including checks that failed audit writes roll back the corresponding workflow change.

GitHub Actions is configured to run the Django checks and test suite against PostgreSQL and Redis on pushes and pull requests. Check the repository's **Actions** tab for the latest result.

## Docker setup

A Dockerfile and Compose configuration are included for the API, PostgreSQL, Redis, a Celery worker, and Celery Beat.

```bash
docker compose up --build -d
```

The container setup has not yet been verified locally because the development machine's Docker engine is unavailable. It should be tested before relying on it for deployment. The current Compose configuration uses development settings and is **not** a production deployment configuration.

## Design notes

- Procurement operations are grouped in service functions where transactions and business validations can be handled together.
- Queries and permissions are scoped to the authenticated user's company.
- Audit records are written within the same transaction as the business operation, so a failed audit write does not leave a partially recorded change.
- Celery handles work that should not block an API request, while the database-backed scheduler supports recurring tasks.

## Status

ProcureFlow is a backend portfolio project. The API, automated tests, audit logging, OpenAPI documentation, and CI configuration are implemented. Docker configuration is included but still needs a successful end-to-end run. Production deployment is not yet documented.
