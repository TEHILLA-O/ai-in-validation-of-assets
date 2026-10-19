# Conventions

Amounts are absolute currency units. A file states its scale (`units`, `thousands`, `millions`, `billions`) and the importer multiplies once. Mixed currencies in one file are rejected. A blank cell stays missing. It is not stored as zero.

An optional operating-cost line is set to zero only when the historical statement is marked complete and the line is absent. That choice is traced.

Expenses and capex are stored as positive amounts and subtracted where the identity requires it. A revolver draw is signed: positive is a draw.

Operating net working capital is receivables, inventory and other operating current assets, minus payables, accrued expenses and other operating current liabilities. Cash and interest-bearing debt are outside it. An increase reduces unlevered free cash flow and operating cash flow.

Forecast working-capital balances are period-end balances: `Revenue × DSO / days`, and the same pattern for inventory and payables using COGS. Historical days use an average balance when the prior close exists, otherwise the ending balance. The method is labelled on the trace.

Two loss pools are kept apart. Book tax follows profit before tax. Unlevered tax follows EBIT. The interest tax shield is in WACC, through the marginal tax rate, not through the historical effective rate.

The equity bridge starts from enterprise value and the last historical balance sheet. Excess cash is cash above the operating-cash requirement. Forecast cash is already inside the cash flow statement and is not added again. Operating cash is not added to equity. If shares are missing or not positive, value per share is not calculated.

Cost mode `line_item` applies the cost drivers and reports margins. Cost mode `margin_target` uses the gross and EBITDA margin assumptions and does not also apply the line-item drivers. The result states which mode ran.

The default interest convention is the opening balance, which does not create a circular revolver. Average and closing balances are solved with a bounded bisection. If it does not converge, the check fails. The model does not insert a plug.

There is no live market data. Risk-free rates, beta, the equity risk premium and market values of debt and equity are inputs with a source and a date. A book-value capital structure is labelled as a proxy.
