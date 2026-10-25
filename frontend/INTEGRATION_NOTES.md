# ProcureFlow frontend integration

This archive contains only the React frontend. The existing Django backend is unchanged.

## Verified against backend source
- POST /api/auth/login/ (JWT)
- GET /api/auth/me/ (returns user role and company)
- GET /api/purchase-requests/, /api/suppliers/, /api/purchase-orders/
- GET /api/rfqs/ and /api/quotes/ restricted to ADMIN / PROCUREMENT_OFFICER.
- POST /api/purchase-requests/ is available to EMPLOYEE accounts only.

## Setup
1. Back up your existing frontend directory.
2. Replace it with this `frontend` folder.
3. Run `npm install`, `npm run build`, and `npm run dev`.
4. Run Django on http://127.0.0.1:8000 for Vite proxy `/api`.

## Important limitations
- The uploaded backend has no company registration endpoint. Therefore the UI does not offer a misleading Register Company form.
- The existing backend's general `/api/auth/register/` creates users without company membership and is intentionally not used by this frontend.
- Tokens are held in memory; refreshing the page signs out. A more durable auth mechanism would require a deliberate security review.
- Backend integration was reviewed against source code, but end-to-end live database tests were not possible here.
- TypeScript compilation succeeded (`tsc -b`); Vite/Vitest could not complete because the archived node_modules lacks Linux Rollup native optional dependency. Install dependencies fresh on your machine.
