# ResQNet Food Bank Allocation

ResQNet is a React/Vite operations dashboard with a FastAPI backend. Allocation
Planning uses a Python OR-Tools MILP model with the SCIP solver.

## Prerequisites

- Node.js 18 or newer and npm 9 or newer
- Python 3.12

## Run locally

Open two PowerShell terminals from the repository root.

### 1. Start the backend

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

The API is at `http://localhost:8000`; interactive API documentation is at
`http://localhost:8000/docs`.

### 2. Start the frontend

```powershell
npm install
npm run dev
```

Open the local address printed by Vite (by default, `http://localhost:3000`).
Allocation Planning connects to `http://localhost:8000/api/v1`. To use another
backend URL, set `VITE_API_BASE_URL` in the repository-root `.env` file.

The optimizer starts with an empty dataset. Enter donor, facility, beneficiary,
packet recipe, and cost inputs in Allocation Planning before running SCIP.
Recipes and ingredient quantities are administrator-configured inputs, not
nutritional recommendations.

## Test and build

Run backend tests from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
```

Run frontend tests and create a production build:

```powershell
npm test
npm run build
```

For optimizer model details, API routes, and configuration, see backend/README.md.
