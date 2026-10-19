# Architecture

The calculation engine in `financial_engine` is the only place that produces statements, WACC, free cash flow and enterprise value. The API stores inputs and outputs. The React application displays them and edits assumptions. Excel export writes formulas that follow the same identities. The analyst reads stored results.

```text
historical statements and assumptions
        -> financial_engine.run_model
        -> ModelResult
        -> API JSON, integrity checks, Excel workbook, analyst brief
```

`CompanyModel` is the input. `ModelResult` is the output. A model version stores the input snapshot. A valuation run stores that same snapshot again plus the output, so an older run can be opened without recalculating it.

The dependency order is fixed:

1. Historical statements
2. Revenue drivers
3. Operating costs
4. EBITDA
5. Capex and depreciation layers
6. EBIT
7. Debt and interest
8. Tax and net income
9. Working capital
10. Financing and dividends
11. Cash flow statement
12. Balance sheet
13. Unlevered free cash flow
14. WACC
15. DCF
16. Equity bridge

Bull, bear and custom scenarios are full assumption sets passed back through `run_model`. Sensitivity tables that change WACC or the terminal assumption re-discount the base unlevered free cash flow. Tables that change growth, margin, capex or working-capital days rebuild the statements.

Amounts use `Decimal`. Floats are rejected at the boundary. Display rounding in the interface does not feed back into the engine.
