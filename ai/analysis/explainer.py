"""Deterministic explanations. Figures are quoted from the calculation engine."""

from __future__ import annotations

from decimal import Decimal


def _text(value) -> str:
    if value is None:
        return "not calculated"
    return str(value)


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def analyse(model: dict, result: dict, topic: str, question: str) -> dict:
    """Explain a stored valuation. This function does not change assumptions or recompute them."""
    question_lower = question.lower()
    refused = any(word in question_lower for word in ("set ", "change the", "update the assumption", "make growth", "override"))
    facts, assumptions, interpretation, questions = _topic(model, result, topic)
    if refused:
        interpretation.insert(
            0,
            "No assumption was modified. Proposed changes have to be entered in the model and recalculated by the financial engine.",
        )
    return {
        "source": "deterministic",
        "topic": topic,
        "question": question,
        "facts": facts,
        "assumptions": assumptions,
        "interpretation": interpretation,
        "questions_for_the_analyst": questions,
        "assumption_changes_applied": False,
    }


def _topic(model: dict, result: dict, topic: str):
    handlers = {
        "enterprise_value": _enterprise,
        "wacc": _wacc,
        "margins": _margins,
        "history": _history,
        "scenarios": _scenarios,
        "inconsistencies": _checks,
        "ratios": _ratios,
        "plausibility": _plausibility,
        "filings": _filings,
        "questions": _questions,
    }
    handler = handlers.get(topic, _enterprise)
    return handler(model, result)


def _enterprise(model: dict, result: dict):
    dcf = result.get("dcf") or {}
    equity = result.get("equity") or {}
    facts = [
        f"Enterprise value is {_text(dcf.get('enterprise_value'))} {result.get('currency')}.",
        f"Present value of explicit unlevered free cash flow is {_text(dcf.get('pv_explicit'))}.",
        f"Terminal value is {_text(dcf.get('terminal_value'))}. Its present value is {_text(dcf.get('pv_terminal'))}.",
        f"The selected terminal method is {_text(dcf.get('terminal_method'))}. The discount convention is {_text(dcf.get('convention'))}.",
        f"Equity value is {_text(equity.get('equity_value'))}. Value per share is {_text(equity.get('value_per_share'))}.",
        f"Engine version {result.get('engine_version')}. Scenario {result.get('scenario_name')}.",
    ]
    if result.get("blocking_errors"):
        facts.append("The forecast did not complete: " + " ".join(result["blocking_errors"]))
    assumptions = [
        f"WACC used for discounting is {_text(dcf.get('wacc'))}.",
        f"Terminal growth stored on this run is {_text(dcf.get('terminal_growth'))}.",
        f"Exit multiple stored on this run is {_text(dcf.get('exit_multiple'))}.",
    ]
    interpretation = list(dcf.get("warnings") or [])
    share = _dec(dcf.get("terminal_share_of_ev"))
    if share is not None and share > Decimal("0.70"):
        interpretation.append(
            f"Terminal value is {_text(dcf.get('terminal_share_of_ev'))} of enterprise value. "
            "That concentration is a warning already raised by the engine, not an adjustment to the value."
        )
    if result.get("synthetic"):
        interpretation.append(result.get("synthetic_notice") or "The company is marked synthetic.")
    return facts, assumptions, interpretation, [
        "Which operating driver moves enterprise value most when it is edited and the model is recalculated?",
        "Is the terminal method the one you intend to rely on, with the other method kept as a cross-check?",
    ]


def _wacc(model: dict, result: dict):
    wacc = result.get("wacc") or {}
    inputs = ((model.get("assumptions") or {}).get("wacc") or {})
    facts = [
        f"WACC is {_text(wacc.get('wacc'))}.",
        f"Cost of equity is {_text(wacc.get('cost_of_equity'))}.",
        f"Pre-tax cost of debt is {_text(wacc.get('pre_tax_cost_of_debt'))}. After-tax cost of debt is {_text(wacc.get('after_tax_cost_of_debt'))}.",
        f"Equity weight is {_text(wacc.get('equity_weight'))}. Debt weight is {_text(wacc.get('debt_weight'))}.",
        f"Capital structure method is {_text(wacc.get('capital_structure_method'))}.",
    ]
    assumptions = [
        f"Risk-free rate { _text(inputs.get('risk_free_rate')) }, source: {_text(inputs.get('risk_free_source'))}, as of {_text(inputs.get('risk_free_as_of'))}.",
        f"Beta { _text(inputs.get('beta')) }, source: {_text(inputs.get('beta_source'))}, as of {_text(inputs.get('beta_as_of'))}.",
        f"Equity risk premium { _text(inputs.get('equity_risk_premium')) }, source: {_text(inputs.get('erp_source'))}.",
        f"Marginal tax rate { _text(inputs.get('marginal_tax_rate')) }. The after-tax debt cost uses this rate, not the historical effective tax rate.",
        f"Market value source: {_text(inputs.get('market_value_source'))}.",
    ]
    return facts, assumptions, list(wacc.get("warnings") or []), [
        "Are the market values of equity and debt dated, and are they market values rather than book values?",
        "Is the marginal tax rate the rate that applies to the interest tax shield?",
    ]


def _margins(model: dict, result: dict):
    facts = []
    for year in result.get("years") or []:
        ratios = year.get("ratios") or {}
        facts.append(
            f"{year.get('label')}: gross margin {_text(ratios.get('gross_margin'))}, "
            f"EBITDA margin {_text(ratios.get('ebitda_margin'))}, "
            f"operating margin {_text(ratios.get('operating_margin'))}, "
            f"net margin {_text(ratios.get('net_margin'))}."
        )
    assumptions = [result.get("cost_precedence_note") or "Cost precedence was not recorded."]
    interpretation = []
    forecast = [year for year in result.get("years") or [] if year.get("is_forecast")]
    if len(forecast) >= 2:
        first = _dec((forecast[0].get("ratios") or {}).get("ebitda_margin"))
        last = _dec((forecast[-1].get("ratios") or {}).get("ebitda_margin"))
        if first is not None and last is not None and abs(last - first) > Decimal("0.05"):
            interpretation.append(
                f"Forecast EBITDA margin moves from {_text((forecast[0].get('ratios') or {}).get('ebitda_margin'))} "
                f"to {_text((forecast[-1].get('ratios') or {}).get('ebitda_margin'))}."
            )
    return facts, assumptions, interpretation, [
        "Which cost lines are percentages of revenue, and which are independent drivers?",
        "Does a margin target override the line-item cost forecast? The cost-mode note is the precedence rule.",
    ]


def _history(model: dict, result: dict):
    facts = []
    for year in result.get("years") or []:
        if year.get("is_forecast"):
            continue
        income = year.get("income") or {}
        facts.append(
            f"{year.get('label')} revenue {_text(income.get('revenue'))}, "
            f"EBITDA {_text(income.get('ebitda'))}, net income {_text(income.get('net_income'))}."
        )
    assumptions = [f"{key}: {value}" for key, value in (result.get("suggestions") or {}).items()]
    interpretation = [
        "Suggestions describe history. They are not copied into the forecast assumptions.",
    ]
    if result.get("synthetic"):
        interpretation.append(result.get("synthetic_notice") or "Synthetic company.")
    return facts, assumptions, interpretation, [
        "Do the historical totals reconcile to the line items, or did a reported total differ from the sum?",
        "Were any optional lines set to zero only because the statement was marked complete?",
    ]


def _scenarios(model: dict, result: dict):
    facts = [_base_value("Base", result)]
    for name, case in (result.get("scenarios") or {}).items():
        facts.append(_base_value(name, case))
    assumptions = [
        "Bull and bear cases recalculate the statements from their own operating assumptions.",
        "Enterprise value is not multiplied by a fixed scenario factor.",
    ]
    return facts, assumptions, [], [
        "Which single assumption differs between the cases you are comparing?",
        "Do the cases share the same WACC and terminal method, or were those edited too?",
    ]


def _base_value(name: str, result: dict) -> str:
    dcf = result.get("dcf") or {}
    equity = result.get("equity") or {}
    return (
        f"{name} enterprise value {_text(dcf.get('enterprise_value'))}, "
        f"equity value {_text(equity.get('equity_value'))}, "
        f"value per share {_text(equity.get('value_per_share'))}."
    )


def _checks(model: dict, result: dict):
    facts = []
    for check in result.get("checks") or []:
        if check.get("status") != "pass" or check.get("severity") == "warning":
            facts.append(
                f"{check.get('name')} ({check.get('period') or 'model'}): {check.get('status')}, "
                f"expected {_text(check.get('expected'))}, actual {_text(check.get('actual'))}. "
                f"{check.get('cause')}"
            )
    if not facts:
        facts.append("No failed checks or warnings were stored on this run.")
    return facts, [], [], ["Which failed check is caused by a missing input rather than an identity error?"]


def _ratios(model: dict, result: dict):
    return _margins(model, result)


def _plausibility(model: dict, result: dict):
    assumptions_in = model.get("assumptions") or {}
    valuation = assumptions_in.get("valuation") or {}
    facts = []
    interpretation = []
    growths = assumptions_in.get("growth_rates") or {}
    for year, rate in growths.items():
        value = _dec(rate)
        facts.append(f"Revenue growth {year} is {_text(rate)}.")
        if value is not None and value > Decimal("0.25"):
            interpretation.append(f"Revenue growth of {_text(rate)} in {year} is above 25%. Confirm that it is intended.")
    terminal = _dec(valuation.get("terminal_growth"))
    wacc = _dec((result.get("wacc") or {}).get("wacc"))
    if terminal is not None and wacc is not None and wacc - terminal < Decimal("0.01"):
        interpretation.append("WACC is within one percentage point of terminal growth. The Gordon value is highly sensitive there.")
    if not interpretation:
        interpretation.append("No growth or WACC-spread warning was triggered by these stored assumptions.")
    return facts, [result.get("cost_precedence_note") or ""], interpretation, [
        "Is long-run growth below the discount rate for a reason you can defend?",
    ]


def _filings(model: dict, result: dict):
    facts = []
    for period in model.get("historical") or []:
        sources = period.get("sources") or {}
        labels = sorted({str((source or {}).get("source") or "source not recorded") for source in sources.values()})
        facts.append(f"{period.get('label')} sources: {', '.join(labels) if labels else 'no source recorded'}.")
    if not facts:
        facts.append("No historical periods are stored, so there are no filing sources to summarise.")
    interpretation = [
        "Uploaded PDF text is not extracted. A language model is not given raw filings unless you explicitly consent, and it is not allowed to replace these sources.",
    ]
    return facts, [], interpretation, [
        "Which line items were mapped from an original label, and which were entered directly?",
    ]


def _questions(model: dict, result: dict):
    facts = ["These questions follow from the stored model. They are not a valuation."]
    return facts, [], [], [
        "What evidence supports the revenue growth path in each forecast year?",
        "Are receivables, inventory and payables consistent with the days assumptions?",
        "Does capital expenditure maintain the asset base implied by depreciation?",
        "Is the debt balance a market value or a book balance carried into the equity bridge?",
        "How much of enterprise value is the present value of the terminal value?",
        "Are there non-operating assets or claims missing from the equity bridge?",
    ]
