
# ProcureFlow

**Procurement Management System**

ProcureFlow is a full-stack web application for managing procurement workflows across organizations. It brings purchase requests, approvals, supplier quotations, purchase orders, and goods receiving into one centralized platform.

Built with **React, TypeScript, Django REST Framework, and PostgreSQL**, the application combines an interactive dashboard with secure authentication, role-based permissions, company-scoped data access, and auditable workflows.

## Live Demo

**[Launch ProcureFlow](https://procureflow-app.onrender.com/)**

The application is deployed on Render, with PostgreSQL hosted on Neon. The live environment includes sample procurement data.

## Key Features

- **Interactive Dashboard:** Overview of purchase requests, suppliers, RFQs, and purchase orders.
- **Purchase Requests:** Create, submit, approve, and reject purchase requests.
- **Supplier Management:** Manage supplier records and quotations.
- **RFQs & Quotations:** Request, compare, and select supplier quotations.
- **Purchase Orders:** Manage purchasing operations and order fulfillment.
- **Goods Receiving:** Track partially and fully received orders.
- **Role-Based Access:** JWT authentication with Employee, Manager, Procurement Officer, and Admin roles.
- **Company-Scoped Data:** Associate users and procurement records with their respective companies.
- **Audit Logging:** Track important actions and workflow changes.
- **Background Tasks:** Celery and Redis support notifications and scheduled reminders.

## Workflow

```text
Purchase Request
       |
       v
Submit for Approval
       |
       +---- Rejected
       |
       v
Approved
       |
       v
Request for Quotation
       |
       v
Supplier Quotations
       |
       v
Select Quotation
       |
       v
Purchase Order
       |
       v
Goods Receiving
       |
       v
Completed
```

Business rules and workflow transitions are validated on the backend.

## Tech Stack

| Area | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend | Python, Django, Django REST Framework |
| Database | PostgreSQL, Neon |
| Authentication | JWT, RBAC |
| Background Tasks | Celery, Redis |
| API Documentation | OpenAPI, Swagger UI |
| Testing | pytest, pytest-django |
| DevOps | Docker, GitHub Actions |
| Deployment | Render |

## Running Locally

**1. Clone the repository**

```bash
git clone https://github.com/Shatha-AbuShammala/procureflow.git
cd procureflow
```

**2. Backend setup**

Requires Python 3.11 and PostgreSQL.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file with your Django secret key and PostgreSQL connection settings. See the Django configuration for the required environment variables.

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
python manage.py migrate
python manage.py runserver
```

**3. Frontend setup**

Open another terminal:

```powershell
cd frontend
npm install
```

Create `frontend/.env`:

```dotenv
VITE_API_BASE=http://127.0.0.1:8000
```

Start the application:

```powershell
npm run dev
```

Open **http://localhost:5173/**.

Redis and Celery are required only when running background tasks and scheduled reminders.

## Architecture & Testing

- React handles the user interface and communicates with the Django REST API.
- Django enforces authentication, role-based permissions, and procurement business rules.
- PostgreSQL stores company, user, and procurement records.
- Audit logs are written within the same database transaction as the associated business operation.
- Automated backend tests use pytest, with GitHub Actions configured for continuous integration.
- Docker configuration is included for backend services but has not yet been fully verified.

**[Explore the Live Application](https://procureflow-app.onrender.com/)**
