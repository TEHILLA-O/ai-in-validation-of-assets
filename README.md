# ValuationLab

ValuationLab is a three-statement forecasting and discounted-cash-flow application. Historical figures, assumptions and market inputs are stored separately from valuation results. Every valuation number is produced by the Python calculation engine. The optional analyst quotes those results and does not calculate them.

Northline Industrial, loaded for the demo user, is a **synthetic** company. It is not a filing, a market price or a recommendation.

## Run locally

Python 3.12 or newer and Node 22 are required.

```powershell
python -m pip install -e ".[dev]"
python -m uvicorn backend.app.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Sign in with the demo account `demo` / `demo-valuationlab`.

The API is at http://127.0.0.1:8000. Interactive docs are at http://127.0.0.1:8000/docs. With no `DATABASE_URL`, the API uses `valuationlab.db` in the working directory. Set `DATABASE_URL` to a Postgres URL when you do not want SQLite. Copy `.env.example` for the other settings.

```powershell
python -m pytest
```

## Docker

```powershell
docker compose up --build
```

The web app is published on port 8080 and the API on port 8000. Compose uses Postgres. Change `VALUATIONLAB_SECRET` before any shared deployment.

## What the demo calculates

The seeded model projects Northline for 2025–2029 from the constructed 2022–2024 statements. Enterprise value, equity value and value per share are outputs of that run. Changing a growth rate creates a new model version and recalculates revenue, profit, working capital, cash flow and enterprise value. Historical 2024 revenue stays as entered.

Display scale in the header divides figures for reading. Stored amounts stay in absolute currency units.

## Honest limits

- Market inputs are typed by the user. There is no live price feed.
- PDF text is not extracted. A PDF upload is stored as a source document and is not turned into statements.
- The Excel workbook's statements, WACC, DCF, WACC-versus-growth grid and WACC-versus-exit-multiple grid use formulas. Discount exponents follow the end-year or mid-year convention on the assumptions sheet. The selected terminal method drives enterprise value. Operating sensitivity tables are values calculated by the engine and are labelled on the sheet, because each cell is a full statement rebuild. The formula sheets match a growth-rate, percentage-cost, percentage-capex, opening-interest case. A different structure is named on the summary instead of being presented as the same formulas.
- OpenPyXL does not calculate workbooks. Formula checks use the Decimal interpreter in `exports/excel/evaluate.py`.
- Quarterly periods are not modelled. Annual periods can carry an explicit day count.
- The language-model provider is off unless `VALUATIONLAB_LLM_API_KEY` is set and the user consents. Consent sends a prepared brief of calculated figures, not uploaded files.
