# ResQNet food allocation optimizer

This service runs the allocation model in Python with Google OR-Tools' SCIP MILP
solver. Inputs start empty; no sample records or precomputed optimization results
are seeded.

## Run locally

From the repository root in PowerShell:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

The API listens on `http://localhost:8000`; OpenAPI documentation is available at
`http://localhost:8000/docs`. The Vite frontend defaults to this API at
`http://localhost:8000/api/v1`. Set `VITE_API_BASE_URL` if the backend is hosted
elsewhere. `RESQNET_DB_PATH` optionally selects the SQLite database location,
and `RESQNET_CORS_ORIGINS` is a comma-separated origin allowlist.

Run backend tests from the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

## API

- `GET /api/v1/health`
- `GET /api/v1/dataset` and `PUT /api/v1/dataset`
- `POST /api/v1/donors`, `/facilities`, `/beneficiaries`, `/packet-types`, `/costs`
- `POST /api/v1/optimize` with `{ "dataset": ..., "options": ... }`
- `GET /api/v1/optimization-results`
- `GET /api/v1/allocation-details/{result_id}`
- `GET /api/v1/equity-analysis/{result_id}`

The Allocation Planning page writes the supplied dataset to SQLite and calls
`POST /optimize`. Each scenario is independently solved and saved with its input
snapshot and solver status. A scenario can be `OPTIMAL`, `FEASIBLE`, or
`INFEASIBLE`; a missing SCIP backend returns an explicit service error.

## Model scope and input units

- Quantities and capacities are kilograms over the configured planning horizon;
  beneficiary demand and packet counts are whole packets.
- `ONCE`, `DAILY`, `WEEKLY`, and `MONTHLY` donor frequencies are expanded into
  horizon totals. Each recipe ingredient is measured in kilograms per packet.
- Costs use one administrator-selected currency unit. Transportation is priced
  per kilometre per kilogram using great-circle distance between the provided
  coordinates.
- Collection, procurement, tier-I to tier-II transfers, packet production and
  delivery, unmet demand, unused food, facility activation, storage expansion,
  vehicle hiring, staffing, and optional unmet-rate equity are decision
  variables or objective terms. Capacity and balance constraints are enforced
  for each food item; results include per-facility item balances and numerical
  maximum constraint residuals/violations.
- Expired donations (expiry before the plan start date) cannot be collected.
  Quantities expiring during the horizon are reported as approaching expiry;
  the current aggregate-horizon model does not make day-by-day expiry or
  inventory-age allocation decisions.
- Beneficiary priority multipliers scale shortage penalties. The optional
  equity objective minimizes the maximum difference between beneficiary
  categories' unmet-demand rates; it is a trade-off against operating cost,
  controlled by the configured equity weight.
- A budget cap constrains modeled operational and penalty costs (not the
  equity-weight term). Results include solver status, objective and cost
  breakdown, allocation tables, utilization, equity, and modeled constraint
  checks. CSV export and browser print-to-PDF are available in the frontend.

Packet recipes and priority weights are administrator inputs, not nutritional
guidance or policy recommendations.
