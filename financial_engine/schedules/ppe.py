"""PP&E and intangible roll-forwards using straight-line vintage layers.

Opening net book value is one layer, charged in equal amounts over its
remaining life. Each year's additions form a new layer. Half-year convention
takes half a charge in the year of addition and keeps the annual charge
unchanged until the residual net book value is smaller than a full charge.

Disposals remove net book value from the oldest layer first. That FIFO rule
is a modelling choice, used because historical gross cost and asset identity
are often unavailable. It is recorded on the schedule.
"""

from __future__ import annotations

from decimal import Decimal

from financial_engine.model import Assumptions, PpeLayer


def opening_layer(name: str, net: Decimal, remaining_life: Decimal) -> list[PpeLayer]:
    if net < 0:
        raise ValueError(f"{name} net book value cannot be negative.")
    if net == 0:
        return []
    if remaining_life <= 0:
        raise ValueError(f"{name} has a positive net book value but no remaining life.")
    # Remaining life can be fractional. The annual charge is net / life, and the
    # layer survives until net is exhausted. charges_left is informational.
    annual = net / remaining_life
    return [PpeLayer(name=name, net=net, annual_charge=annual, charges_left_after_this_year=10**6)]


def _charge_layers(layers: list[PpeLayer]) -> tuple[Decimal, list[PpeLayer]]:
    depreciation = Decimal(0)
    surviving: list[PpeLayer] = []
    for layer in layers:
        if layer.net <= 0:
            continue
        charge = min(layer.annual_charge, layer.net)
        depreciation += charge
        remaining = layer.net - charge
        if remaining > 0:
            surviving.append(
                PpeLayer(
                    name=layer.name,
                    net=remaining,
                    annual_charge=layer.annual_charge,
                    charges_left_after_this_year=max(layer.charges_left_after_this_year - 1, 0),
                )
            )
    return depreciation, surviving


def _consume(layers: list[PpeLayer], amount: Decimal, reason: str) -> tuple[list[PpeLayer], Decimal]:
    """Remove net book value FIFO. Returns layers and any amount that could not be removed."""
    if amount < 0:
        raise ValueError(f"{reason} cannot be negative.")
    left = amount
    kept: list[PpeLayer] = []
    for layer in layers:
        if left == 0:
            kept.append(layer)
            continue
        take = min(layer.net, left)
        left -= take
        remaining = layer.net - take
        if remaining > 0:
            kept.append(
                PpeLayer(
                    name=layer.name,
                    net=remaining,
                    annual_charge=layer.annual_charge,
                    charges_left_after_this_year=layer.charges_left_after_this_year,
                )
            )
    return kept, left


def roll_asset(
    layers: list[PpeLayer],
    additions: Decimal,
    addition_life: Decimal,
    disposals_nbv: Decimal,
    impairment: Decimal,
    half_year: bool,
    addition_name: str,
) -> tuple[list[PpeLayer], dict[str, Decimal]]:
    if additions < 0:
        raise ValueError("Additions cannot be negative. Use disposals for asset sales.")
    layers, unmet_disposal = _consume(layers, disposals_nbv, "Disposals")
    layers, unmet_impairment = _consume(layers, impairment, "Impairment")
    existing_charge, layers = _charge_layers(layers)
    new_charge = Decimal(0)
    if additions > 0:
        if addition_life <= 0:
            raise ValueError("New assets need a positive useful life.")
        annual = additions / addition_life
        first = annual * (Decimal("0.5") if half_year else Decimal(1))
        first = min(first, additions)
        new_charge = first
        residual = additions - first
        if residual > 0:
            layers.append(
                PpeLayer(
                    name=addition_name,
                    net=residual,
                    annual_charge=annual,
                    charges_left_after_this_year=10**6,
                )
            )
    opening_net = sum((layer.net for layer in layers), Decimal(0)) - (
        additions - new_charge
    )
    # opening_net reconstructed above is fragile once disposals already changed layers.
    # The caller passes economic opening separately. This function returns charges and closing.
    closing = sum((layer.net for layer in layers), Decimal(0))
    return layers, {
        "additions": additions,
        "disposals_nbv": disposals_nbv,
        "impairment": impairment,
        "depreciation": existing_charge + new_charge,
        "existing_depreciation": existing_charge,
        "new_depreciation": new_charge,
        "closing_net": closing,
        "unallocated_disposal": unmet_disposal,
        "unallocated_impairment": unmet_impairment,
        "opening_net_after_movements_before_new_residual": opening_net,
    }


def capex_amount(
    assumptions: Assumptions,
    period_id: str,
    revenue: Decimal,
    prior_capex: Decimal | None,
) -> Decimal:
    method = assumptions.capex_method
    if method == "pct_revenue":
        if assumptions.capex_pct_revenue is None:
            raise ValueError("CapEx as a percentage of revenue requires capex_pct_revenue.")
        return revenue * assumptions.capex_pct_revenue
    if method == "fixed":
        if assumptions.capex_fixed is None:
            raise ValueError("Fixed CapEx requires capex_fixed.")
        return assumptions.capex_fixed
    if method == "custom":
        if period_id not in assumptions.capex_custom:
            raise ValueError(f"Custom CapEx is missing for {period_id}.")
        return assumptions.capex_custom[period_id]
    if method == "growth":
        if assumptions.capex_growth is None:
            raise ValueError("CapEx growth requires capex_growth.")
        if prior_capex is None:
            raise ValueError(
                "CapEx growth needs the prior year's capital expenditure. "
                "It is not assumed to be zero when the cash flow statement is missing."
            )
        return prior_capex * (Decimal(1) + assumptions.capex_growth)
    raise ValueError(f"Unknown CapEx method {method}")
