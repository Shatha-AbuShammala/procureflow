# ProcureFlow Frontend

An original Editorial Industrial React + TypeScript frontend for the ProcureFlow Django REST API.

## Quick start (Windows PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173/. The application starts in **DEMO DATA** mode with clearly fictional `.example` contacts. No backend is needed to explore the interface.

## Connect to Django

Start your existing Django backend at http://127.0.0.1:8000. In the frontend, click **Connect Django**, then log in with an existing Django username and password. This uses the real `POST /api/auth/login/` endpoint and queries your actual Django endpoints. Login tokens are held **in memory only**; a refresh signs you out. This is a development/portfolio prototype, not a complete production auth implementation.

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so CORS changes are not needed for the local default. To target a different Django host during local development, create `frontend/.env.local` with `VITE_PROXY_TARGET=http://127.0.0.1:8000` and restart Vite. For a separately hosted frontend, set `VITE_API_BASE=https://YOUR-API-HOST/api`, configure restrictive CORS in Django, and review HTTPS, CSRF, JWT, refresh token strategy and API authorization before production use. Do not put secrets in Vite environment variables.

## Commands

- `npm run dev` — development server
- `npm run build` — TypeScript check and optimized build
- `npm test` — unit tests
- `npm run preview` — preview build

## Included pages

Overview, Purchase Requests, Approvals, Suppliers, RFQs, Supplier Quotes, Purchase Orders, Receiving. Data tables and search are interactive; request creation and status actions are only enabled for authenticated API mode. Receiving is an explanatory screen because the backend has a nested purchase-order action, not a standalone list endpoint.

## Backend mapping

- `/api/auth/login/`, `/api/auth/refresh/`
- `/api/purchase-requests/`, `/api/purchase-requests/{id}/submit/`, `/approve/`, `/reject/`
- `/api/suppliers/`
- `/api/rfqs/`, `/api/quotes/`, `/api/purchase-orders/`

### Important limits

This frontend does **not** repair Django permissions, tenant isolation, Celery/Redis, CORS, deployment, or database settings. Django authorization is the source of truth. Do not use live production credentials in a public demo. Some API actions require roles; 403 is expected for unauthorized users. Real backend response shapes, permission workflows, and integration still require end-to-end testing with a running Django instance. The mock records are examples, not data from your database.


## Role-aware UI updates

After login, the frontend reads `GET /api/auth/me/` and uses the returned role to show relevant actions. Only EMPLOYEE sees New request; only MANAGER sees approval/rejection controls; only the requesting EMPLOYEE sees Submit draft. Django remains the source of truth for permissions.

TypeScript fixes: `src/vite-env.d.ts` declares Vite environment types; status labels use a compatible regex replacement instead of `replaceAll`. The favicon is `public/favicon.svg`.
