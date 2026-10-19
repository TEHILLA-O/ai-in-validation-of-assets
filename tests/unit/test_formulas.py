"""Small formula tests that do not run the full Northline model."""

from decimal import Decimal

from financial_engine.dcf.valuation import gordon_terminal_value, implied_growth, present_value
from financial_engine.forecasts.revenue import forecast_growth, forecast_price_volume
from financial_engine.model import Assumptions, SegmentDriver
from financial_engine.schedules.debt import allocate_repayment
from financial_engine.schedules.tax import tax_and_nol
from financial_engine.schedules.working_capital import ending_balance


def test_growth_and_price_volume_bridge():
    grown = forecast_growth(Decimal("1000"), "2025", Decimal("0.10"))
    assert grown.revenue == Decimal("1100")
    assumptions = Assumptions(
        base_units=Decimal("100"),
        base_price=Decimal("10"),
        volume_growth={"2025": Decimal("0.10")},
        price_growth={"2025": Decimal("0.05")},
    )
    priced = forecast_price_volume(Decimal("100"), Decimal("10"), "2025", assumptions)
    assert priced.units == Decimal("110")
    assert priced.price == Decimal("10.5")
    assert priced.revenue == Decimal("1155")
    assert priced.bridge["volume_contribution"] == Decimal("100")
    assert priced.bridge["price_contribution"] == Decimal("55")


def test_customer_retention_replaces_volume_growth():
    assumptions = Assumptions(
        opening_customers=Decimal("100"),
        retention={"2025": Decimal("0.90")},
        new_customers={"2025": Decimal("20")},
        price_growth={"2025": Decimal("0")},
        base_price=Decimal("10"),
    )
    year = forecast_price_volume(Decimal("100"), Decimal("10"), "2025", assumptions)
    assert year.customers == Decimal("110")
    assert year.revenue == Decimal("1100")


def test_segment_sum_and_tax_loss():
    assert SegmentDriver(name="Products").name == "Products"
    tax, taxable, nol = tax_and_nol(Decimal("-40"), Decimal("10"), Decimal("0.25"))
    assert tax == 0
    assert taxable == 0
    assert nol == Decimal("50")
    tax, taxable, nol = tax_and_nol(Decimal("80"), nol, Decimal("0.25"))
    assert taxable == Decimal("30")
    assert tax == Decimal("7.5")
    assert nol == 0


def test_days_balance_and_repayment_order_and_gordon_guard():
    assert ending_balance(Decimal("36500"), Decimal("10"), 365) == Decimal("1000")
    short, long = allocate_repayment(Decimal("5"), Decimal("20"), Decimal(0), Decimal(0), Decimal("8"))
    assert short == Decimal("5")
    assert long == Decimal("3")
    assert gordon_terminal_value(Decimal("100"), Decimal("0.08"), Decimal("0.08")) is None
    value = gordon_terminal_value(Decimal("100"), Decimal("0.10"), Decimal("0.02"))
    assert value == Decimal("100") * Decimal("1.02") / Decimal("0.08")
    assert present_value(Decimal("110"), Decimal("0.10"), Decimal(1)) == Decimal("100")
    terminal = Decimal("500")
    assert implied_growth(terminal, Decimal("100"), Decimal("0.10")) == (
        terminal * Decimal("0.10") - Decimal("100")
    ) / (terminal + Decimal("100"))
