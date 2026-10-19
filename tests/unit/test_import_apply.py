"""Imported blanks stay missing, and unmapped labels are not invented as zeros."""

from financial_engine.imports.statements import apply_figures, import_csv
from financial_engine.model import Assumptions, CompanyModel


def _model() -> CompanyModel:
    return CompanyModel(
        company_id="sample",
        name="Sample",
        currency="USD",
        historical=[],
        assumptions=Assumptions(),
    )


def test_blank_cell_is_stored_as_missing_and_scale_is_applied():
    payload = (
        "period,line_item,value,currency,unit_scale\n"
        "2024,Revenue,,USD,units\n"
        "2024,Cost of goods sold,12,USD,thousands\n"
        "2024,Mystery fee,4,USD,units\n"
    ).encode()
    imported = import_csv(payload, "sample.csv")
    assert not imported.blocking
    warnings = apply_figures(_model(), imported, "2026-10-19T00:00:00Z")
    assert any("Mystery fee" in warning for warning in warnings)
    model = _model()
    apply_figures(model, imported, "2026-10-19T00:00:00Z")
    period = model.historical[0]
    assert period.income["revenue"] is None
    assert period.income["cogs"] == 12_000
    assert "mystery" not in period.income


def test_mixed_currency_is_refused():
    payload = (
        "period,line_item,value,currency,unit_scale\n"
        "2024,Revenue,10,USD,units\n"
        "2024,Cost of goods sold,4,EUR,units\n"
    ).encode()
    imported = import_csv(payload, "mixed.csv")
    assert imported.blocking
    try:
        apply_figures(_model(), imported, "2026-10-19T00:00:00Z")
    except ValueError as exc:
        assert "currenc" in str(exc).lower()
    else:
        raise AssertionError("Mixed currencies should be refused")
