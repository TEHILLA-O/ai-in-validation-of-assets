# Northline Industrial

Northline Industrial is a synthetic worked example. The notice on the company record says so in the application. None of the figures is a filing extract or a market price.

The construction lives in `financial_engine/reference/northline.py`. Three historical years, 2022 to 2024, already satisfy the statement identities. The forecast is 2025 to 2029. Revenue growth in the base case is 10 percent. Cost of goods sold is 60 percent of revenue. Working-capital days are 36.5 on a 365-day year, so the forecast receivable balance is 10 percent of revenue. Capital expenditure is 5 percent of revenue. Interest is 6 percent of opening debt. The book tax rate is 25 percent. WACC uses a 4 percent risk-free rate, a beta of 1.1, a 5 percent equity risk premium, a 6 percent pre-tax cost of debt, a 25 percent marginal tax rate, market equity of 90,000 and market debt of 20,000. Those market values are labelled as manual synthetic inputs.

The reference test checks 2025 revenue of 110,000, EBITDA of 16,500, net income of 7,432.50, unlevered free cash flow of 7,162.50 and a balanced balance sheet. The workbook formula check repeats those figures, including a mid-year discount case. It also checks that a lower risk-free rate changes enterprise value without changing 2024 revenue, and that a higher interest rate changes interest and financing cash flow without changing EBIT inside unlevered free cash flow.

`docs/examples/import_format_example.csv` is only a file-layout example. It is not the Northline history. Blank cells in that file are meant to stay missing.
