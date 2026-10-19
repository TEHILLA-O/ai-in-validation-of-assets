# Formulas

These are the identities implemented in `financial_engine`. The tests in `tests/financial_reference` recompute the Northline 2025 year from the inputs rather than from the engine's own functions.

```text
Gross profit = Revenue − COGS
EBITDA = Revenue − cash operating costs
EBIT = EBITDA − depreciation − amortisation − impairments
Profit before tax = EBIT + interest income − interest expense + other non-operating items
Net income = Profit before tax − book tax
```

```text
Revenue(t) = Revenue(t−1) × (1 + g(t))
```

Price and volume, and segment sums, are the other revenue methods. A customer model uses opening customers times retention plus new customers, and then ignores the volume-growth rate.

```text
Closing PP&E = Opening PP&E + capex − depreciation − disposal net book value − impairments
Closing debt = Opening debt + borrowings − repayments
Closing retained earnings = Opening retained earnings + net income − dividends
Closing cash = Opening cash + cash from operations + cash from investing + cash from financing
Total assets = Total liabilities + total equity
```

```text
UFCF = EBIT − unlevered tax + depreciation and amortisation − capex + disposal proceeds − increase in operating NWC + other operating adjustments
```

Interest is not deducted in unlevered free cash flow.

```text
Cost of equity = risk-free rate + beta × equity risk premium + country risk premium + other named adjustment
After-tax cost of debt = pre-tax cost of debt × (1 − marginal tax rate)
WACC = equity weight × cost of equity + debt weight × after-tax cost of debt
```

End-of-year present value uses exponent t = 1…N. Mid-year uses t − 0.5.

```text
Gordon terminal value = UFCF(final) × (1 + g) / (WACC − g)    only when WACC > g
Exit terminal value = final EBITDA × exit multiple
Enterprise value = present value of explicit UFCF + present value of terminal value
Equity value = enterprise value − debt and debt-like claims − minority interest − preferred + excess cash + non-operating assets
Value per share = equity value / diluted shares
```

The selected terminal method is the one in enterprise value. The other method is reported beside it.
