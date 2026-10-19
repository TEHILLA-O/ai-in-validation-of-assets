"""The explainer quotes engine output and does not change the model."""

from ai.analysis.explainer import analyse


def _result() -> dict:
    return {
        "engine_version": "1.0.0",
        "currency": "USD",
        "scenario_name": "Base",
        "synthetic": True,
        "synthetic_notice": "SYNTHETIC ILLUSTRATIVE COMPANY.",
        "blocking_errors": [],
        "cost_precedence_note": "Line-item drivers are applied.",
        "suggestions": {},
        "dcf": {
            "enterprise_value": "123456.25",
            "pv_explicit": "40000",
            "terminal_value": "200000",
            "pv_terminal": "83456.25",
            "terminal_method": "gordon",
            "convention": "end",
            "wacc": "0.085",
            "terminal_growth": "0.02",
            "exit_multiple": "8",
            "terminal_share_of_ev": "0.68",
            "warnings": [],
        },
        "equity": {"equity_value": "100000", "value_per_share": "10"},
        "wacc": {
            "wacc": "0.085",
            "cost_of_equity": "0.095",
            "pre_tax_cost_of_debt": "0.06",
            "after_tax_cost_of_debt": "0.045",
            "equity_weight": "0.8",
            "debt_weight": "0.2",
            "capital_structure_method": "market",
            "warnings": [],
        },
        "years": [],
        "checks": [],
        "scenarios": {},
    }


def test_explanation_quotes_the_calculated_enterprise_value():
    brief = analyse({"assumptions": {"wacc": {}}, "historical": []}, _result(), "enterprise_value", "Why is the value this level?")
    combined = " ".join(brief["facts"])
    assert "123456.25" in combined
    assert brief["assumption_changes_applied"] is False
    assert brief["source"] == "deterministic"


def test_explanation_refuses_to_change_an_assumption():
    brief = analyse({"assumptions": {}, "historical": []}, _result(), "enterprise_value", "Please set growth to 50%")
    assert brief["assumption_changes_applied"] is False
    assert any("No assumption was modified" in line for line in brief["interpretation"])
