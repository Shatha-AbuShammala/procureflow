# ProcureFlow technical review

Reviewed on 2026-10-24, on branch `fix/production-readiness`. Changes remain local and uncommitted. No push, merge, or external deployment was performed.

## Issues corrected

| Area | Finding and implemented fix |
| --- | --- |
| Tenant isolation | Quote creation accepted an RFQ and supplier belonging to another company when the two foreign records matched each other. Both writable relationship querysets now scope to the caller's company, with a second ownership check during locked creation. RFQ request/supplier relationship fields are also scoped before validation. |
| Company membership | Purchase request and order endpoints now require an assigned company, consistently with the other procurement endpoints. Existing company read boundaries and employee request ownership are retained. |
| Platform administration | Django's ordinary staff permissions could bypass API tenancy/workflow rules. The admin site now requires an active staff superuser; company admins use the company-scoped API. Platform operators remain trusted administrators. |
| Registration | Registration previously checked password length without invoking configured Django password validators. It now applies all configured validators and continues to exclude privilege and company assignment fields. Concurrent duplicate usernames return a validation error after rollback. |
| JWT | Refresh rotation, blacklisting, short access lifetimes, and password-change revocation are explicit. A guarded refresh serializer handles deleted/inactive accounts and revoked passwords, and locks the outstanding token so concurrent rotation has one winner. A daily task removes expired token records. Existing tokens may require a fresh login after upgrading. |
| Abuse controls | API anonymous/user throttles and stricter login/refresh/registration scopes were added. Production uses a shared Redis cache; nginx also limits authentication and admin login requests. Application throttles are not a substitute for edge traffic controls. |
| Workflow concurrency | Submit/approve/reject and RFQ send/select now lock the parent row before checking state. RFQ and quote creation revalidate after acquiring parent locks. Duplicate decisions, RFQs, quotations, selected quotes, and orders are rejected cleanly under concurrent requests. Receiving retains its order lock. |
| Database integrity | Migration `procurement.0004` adds valid-status checks, positive quantity/price/total checks, nonnegative estimated prices, and a partial unique constraint allowing one selected quotation per RFQ. Existing one-to-one and supplier/RFQ uniqueness constraints are preserved. |
| Input validation | Zero quantities, negative estimated prices, nonpositive quote/order prices, malformed currency codes, empty/duplicate item lists, duplicate RFQ suppliers, invalid decision comments, past RFQ deadlines, and past delivery dates are rejected. Estimated request totals cannot overflow the output monetary field. Same-day delivery and zero estimated prices remain valid. |
| Workflow validity | Expired RFQs cannot be sent or accept quotes. Inactive suppliers cannot quote or be selected. Orders require an approved request, selected quote, closed RFQ, and active company supplier. Only managers decide approvals, and self-approval/rejection is denied. |
| Order matching | Order input incorrectly depended on the caller submitting items in database order. It now matches by request item ID, enforces the exact set and quantities, and compares the computed total with the quotation. Service functions enforce roles and company boundaries independently of views. |
| Receiving | Services reject zero/negative quantities, duplicate items, foreign order items, completed orders, and receipts exceeding the remaining quantities. Audit failure rolls back the receipt, its items, and the order status. |
| Attachments | Development media routes exposed uploaded quotations without authentication. Public media serving is removed. Downloads now use a company-scoped protected action with attachment disposition and private/no-store caching. Upload size, extension, and file signature are checked for PDF/PNG/JPEG. nginx never publishes uploads. |
| Audit records | Quote selection recorded its already-updated status as the old value. It now records the true previous status and RFQ closure. Quote creation is audited. Workflow audit writes remain inside the business transaction, with rollback tests. |
| Background processing | Broker publication errors after commit could return HTTP 500 even though the order had been saved. Publication now has a logged synchronous fallback for the in-application notification and a robust commit callback. Notification creation relies on Django's atomic get-or-create handling and remains idempotent. Tasks retry transient database failures; reminders exclude inactive/moved recipients. |
| Supplier deletion | Deleting a supplier with protected procurement references could raise an uncaught database exception. It returns an actionable validation error; historical suppliers can be deactivated. |
| Settings | Production settings were effectively empty. They now reject weak/missing secrets and missing/wildcard/empty hosts, enforce HTTPS/cookies/HSTS/security headers, configure shared cache, database connection health checks, static manifests, and logging. Production does not automatically load development dotenv files. WSGI/ASGI/Celery default to production; local management commands default to development. |
| Environment/dependencies | The environment example used POSTGRES_* names although Django expected DB_*. It now matches the application. All existing runtime packages are pinned in base requirements, development/production additions are separated, and the root UTF-16 freeze was replaced with a readable UTF-8 requirements entry point. The PostgreSQL binary driver is explicitly pinned and audited. |
| Ignored artifacts | Environment variants, uploads, collected static assets, TLS keys/certificates, and scheduler artifacts are ignored. Secrets and generated content are excluded from images. Text line endings are normalized for Linux containers and Windows editing. |
| Containers | Workers and Beat could start before migrations. Development and production stacks now use one initialization service and dependency conditions. The application image runs as an unprivileged user, production excludes test dependencies, and data/uploads/static files persist in appropriate volumes. |
| Deployment | Added separate production Compose, Gunicorn configuration, nginx TLS termination, private service networking, static serving, health checks, worker health checks, Redis persistence, graceful worker shutdown, and safe proxy-header handling. nginx resolves the backend through Docker DNS after container recreation. |
| Documentation/CI | README now documents architecture, role boundaries, exact local/Docker commands, provisioning, API routes, JWT rotation, tests, deployment and rollback prerequisites, and operational limits. OpenAPI actions have accurate request/response annotations. CI adds migration/schema/deployment/static/dependency/Compose checks and a production image build. |

## Files changed

| Files | Purpose |
| --- | --- |
| `apps/accounts/{permissions,serializers,views,urls}.py` | Company membership, password validation, safe token refresh, registration race handling, throttled authentication. |
| `apps/core/{apps,admin,views}.py` | Platform-only admin registration and liveness/readiness handlers. |
| `apps/procurement/models.py`, `migrations/0004_enforce_procurement_integrity.py` | Validators and database constraints. |
| `apps/procurement/{serializers,views,services}.py` | Tenant-safe relationships, validated workflows, transactions, locks, order matching, attachment access, correct audit records, and schema annotations. |
| `apps/suppliers/views.py` | Protected deletion errors and safe schema introspection. |
| `apps/notifications/tasks.py` | Reliable post-commit behavior, retries, recipient checks, token cleanup, and efficient reminder relationships. |
| `config/settings/{base,prod,test}.py` | Shared security defaults, hardened production configuration, isolated PostgreSQL test configuration. |
| `config/{urls,wsgi,asgi,celery}.py` | Health routes, removal of public upload serving, secure process defaults. |
| `requirements.txt`, `requirements/{base,dev,prod}.txt` | Consistent pinned dependency sets and UTF-8 root entry point. |
| `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml` | Development/production images, service startup ordering, isolation, persistent storage, health checks. |
| `gunicorn.conf.py`, `deploy/nginx.conf` | Production process configuration, TLS proxy, static files, request limits, protected media. |
| `.env.example`, `.env.production.example` | Correct local variables and explicit production configuration template. |
| `.gitignore`, `.dockerignore`, `.gitattributes` | Secret/generated-file exclusions and portable text files. |
| `pytest.ini`, `tests/conftest.py` | Dedicated test settings, isolated throttle caches, shared fixtures. |
| `tests/test_purchase_orders.py` | Relative dates and fixtures consistent with completed RFQ selection; all existing assertions retained. |
| `tests/test_{security,workflow_integrity,health,production_settings}.py` | New security, workflow, concurrency, rollback, database, health, and deployment configuration regressions. |
| `.github/workflows/ci.yml` | Expanded validation and production image build on CI. |
| `README.md`, this report | Setup, architecture, API, operations, verification results, and limitations. |

## Verification

- Full PostgreSQL suite: **124 passed, 0 failed, 0 skipped**, in 102.55 seconds. All original tests are retained. This includes concurrent registration, refresh rotation, approval/rejection, RFQ/quote/order creation, selection, and receiving.
- Django system checks, migration consistency, strict OpenAPI schema validation, production deployment checks, and production static collection have passed.
- Production static collection copied and post-processed 154 files.
- Development and production Compose configurations passed `docker compose ... config --quiet`. These checks do not start containers.
- `pip check` passed. The pinned requirements vulnerability audit reported no known vulnerabilities; the final audit includes the explicitly pinned PostgreSQL binary driver.
- Python compilation passed. Black checked all 28 modified/new Python files successfully. Git whitespace checks passed.
- A read-only preflight of the existing local database found zero violations in the eight checks run: request item quantities/prices, quote totals, multiple selected quotes, request/requester company, quote/supplier company, order item quantities/prices, receiving quantities, and receipt/order-item order consistency. This was not a complete historical-data audit and did not change records.

## Remaining deployment work and limits

No known unresolved critical application defect was identified after these fixes. This is a code and local verification review, not a guarantee of security or an external penetration test.

- The local Docker daemon is unavailable: the CLI reports that `//./pipe/docker_engine` does not exist. A production image build, nginx/TLS runtime, complete Compose startup, and the actual Linux Gunicorn/Celery/Beat deployment have not been verified locally. CI contains build validation but was not triggered or claimed to have passed.
- Run the complete stack in staging with real PostgreSQL/Redis, exercise the full HTTP workflow, receive scheduled reminders, and verify worker/scheduler health before deploying.
- Set deployment secrets, real hostnames, trusted HTTPS origins, certificates/renewal, DNS, firewall rules, resource budgets, backups/restore testing, and monitoring. Review the production HSTS/subdomain policy for the actual domain.
- Rehearse migration `0004` on a backup. Invalid historical data will deliberately block constraint installation; no existing business data was rewritten by this review. Application tests apply migrations to a separate disposable database.
- Before exposing the new private-download API, remove any old public web-server/object-storage mappings to the upload directory.
- Dependency scanning checked pinned package versions against published advisories at review time with `--no-deps --disable-pip`. It is not a container/OS vulnerability scan or a fresh Linux dependency installation. Scan the built image and repeat dependency checks before release.
- API list response shapes remain unchanged and unpaginated; assess dataset size and add versioned pagination if required. Existing role semantics, including company-wide order reads, are documented rather than silently changed.
- Notifications are in-application database records. There is no email integration or general durable outbox. Broker publication has a local fallback, but callback/database/worker failures still require operational monitoring.
- POST receiving has no client idempotency key. Duplicate item rows and over-receiving are blocked; clients should reconcile receipt history before retrying an uncertain successful POST, since repeated partial receipts may be legitimate separate deliveries.
- Cross-table tenant consistency is enforced by the API/services, with database checks for local invariants. Trusted platform operators and direct SQL scripts must preserve those relationships; the project does not implement PostgreSQL row-level security.

## References used during review

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django row locking](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)
- [Simple JWT configuration](https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html)
- [Celery configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html)

Exact local startup and deployment preparation commands are in the [README](../README.md).
