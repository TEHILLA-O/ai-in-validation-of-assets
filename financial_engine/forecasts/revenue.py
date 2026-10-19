"""Revenue forecasting.

Three methods are supported. Total revenue is always the sum of the pieces
that the active method actually uses. Inactive methods are reported as ignored
so a margin or growth input cannot silently double-count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from financial_engine.model import Assumptions, SegmentDriver


@dataclass
class RevenueYear:
    revenue: Decimal
    units: Decimal | None = None
    price: Decimal | None = None
    customers: Decimal | None = None
    bridge: dict[str, Decimal | None] = field(default_factory=dict)
    segments: dict[str, Decimal] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _rate(mapping: dict[str, Decimal], period_id: str, default: Decimal = Decimal(0)) -> Decimal:
    return mapping.get(period_id, default)


def forecast_growth(
    prior_revenue: Decimal,
    period_id: str,
    growth: Decimal,
) -> RevenueYear:
    revenue = prior_revenue * (Decimal(1) + growth)
    return RevenueYear(
        revenue=revenue,
        bridge={
            "prior_revenue": prior_revenue,
            "growth_rate": growth,
            "growth_contribution": revenue - prior_revenue,
            "price_contribution": None,
            "volume_contribution": None,
            "segment_contribution": None,
        },
        notes=["Revenue(t) = Revenue(t-1) × (1 + growth rate(t))."],
    )


def forecast_price_volume(
    prior_units: Decimal,
    prior_price: Decimal,
    period_id: str,
    assumptions: Assumptions,
    *,
    segment: SegmentDriver | None = None,
    prior_customers: Decimal | None = None,
) -> RevenueYear:
    volume_growth = _rate(
        segment.volume_growth if segment else assumptions.volume_growth,
        period_id,
    )
    price_growth = _rate(
        segment.price_growth if segment else assumptions.price_growth,
        period_id,
    )
    notes: list[str] = []
    customers = None
    retention_map = segment.retention if segment else assumptions.retention
    new_map = segment.new_customers if segment else assumptions.new_customers
    opening_customers = segment.opening_customers if segment else assumptions.opening_customers
    use_customers = bool(retention_map or new_map or opening_customers is not None or prior_customers is not None)
    if use_customers:
        retention = _rate(retention_map, period_id, Decimal(1))
        new_customers = _rate(new_map, period_id, Decimal(0))
        # prior_customers is the modelled closing balance of the previous forecast year.
        # opening_customers is only the historical seed, used in the first forecast year.
        base_customers = prior_customers if prior_customers is not None else opening_customers
        if base_customers is None:
            base_customers = prior_units
        customers = base_customers * retention + new_customers
        units = customers
        notes.append(
            "Customer identity: ending customers = opening customers × retention + new customers. "
            "Units sold equal ending customers. Volume growth is not also applied."
        )
    else:
        units = prior_units * (Decimal(1) + volume_growth)
    price = prior_price * (Decimal(1) + price_growth)
    arpu_map = segment.arpu if segment else assumptions.arpu
    if period_id in arpu_map:
        price = arpu_map[period_id]
        notes.append("Average selling price was replaced by the period ARPU assumption.")
    revenue = units * price
    volume_effect = (units - prior_units) * prior_price
    price_effect = (price - prior_price) * units
    return RevenueYear(
        revenue=revenue,
        units=units,
        price=price,
        customers=customers,
        bridge={
            "prior_revenue": prior_units * prior_price,
            "growth_rate": None,
            "growth_contribution": None,
            "volume_contribution": volume_effect,
            "price_contribution": price_effect,
            "segment_contribution": None,
        },
        notes=notes
        + [
            "Revenue = units × average selling price.",
            "Volume effect = change in units × prior price.",
            "Price effect = change in price × current units.",
        ],
    )


def forecast_revenue_year(
    assumptions: Assumptions,
    period_id: str,
    prior_revenue: Decimal,
    prior_units: Decimal | None,
    prior_price: Decimal | None,
    segment_state: dict[str, tuple[Decimal, Decimal | None, Decimal | None]],
    prior_customers: Decimal | None = None,
) -> tuple[RevenueYear, dict[str, tuple[Decimal, Decimal | None, Decimal | None]], list[str]]:
    """Return the year, updated segment state, and ignored-driver notes."""
    ignored: list[str] = []
    if assumptions.revenue_method == "growth":
        growth = assumptions.growth_rates.get(period_id)
        if growth is None:
            raise ValueError(f"Growth rate missing for {period_id}")
        year = forecast_growth(prior_revenue, period_id, growth)
        if assumptions.segments:
            ignored.append("Segment drivers are stored but ignored because the revenue method is growth.")
        return year, segment_state, ignored

    if assumptions.revenue_method == "price_volume":
        if prior_units is None or prior_price is None:
            raise ValueError("Price and volume forecasting requires a base unit volume and price.")
        year = forecast_price_volume(
            prior_units,
            prior_price,
            period_id,
            assumptions,
            prior_customers=prior_customers,
        )
        if assumptions.segments:
            ignored.append("Segment drivers are stored but ignored because the revenue method is price and volume.")
        return year, segment_state, ignored

    if not assumptions.segments:
        raise ValueError("Segment forecasting requires at least one revenue segment.")
    total = Decimal(0)
    bridges_volume = Decimal(0)
    bridges_price = Decimal(0)
    new_state: dict[str, tuple[Decimal, Decimal | None, Decimal | None]] = {}
    segment_revenue: dict[str, Decimal] = {}
    notes: list[str] = ["Total revenue is the sum of the segment forecasts."]
    for segment in assumptions.segments:
        prev = segment_state.get(segment.name)
        if segment.method == "growth":
            if prev is None:
                if segment.base_revenue is None:
                    raise ValueError(f"Segment {segment.name} needs a base revenue.")
                prev_rev = segment.base_revenue
            else:
                prev_rev = prev[0]
            growth = segment.growth_rates.get(period_id)
            if growth is None:
                raise ValueError(f"Segment {segment.name} has no growth rate for {period_id}")
            piece = forecast_growth(prev_rev, period_id, growth)
            new_state[segment.name] = (piece.revenue, None, None)
        else:
            customer_model = bool(segment.retention or segment.new_customers or segment.opening_customers is not None)
            if prev is None or prev[1] is None or prev[2] is None:
                if segment.base_units is None or segment.base_price is None:
                    raise ValueError(f"Segment {segment.name} needs base units and price.")
                units = segment.base_units
                price = segment.base_price
                prior_customers = None
            else:
                units, price = prev[1], prev[2]
                prior_customers = units if customer_model else None
            piece = forecast_price_volume(
                units,
                price,
                period_id,
                assumptions,
                segment=segment,
                prior_customers=prior_customers,
            )
            new_state[segment.name] = (piece.revenue, piece.units, piece.price)
            if piece.bridge.get("volume_contribution") is not None:
                bridges_volume += piece.bridge["volume_contribution"]
            if piece.bridge.get("price_contribution") is not None:
                bridges_price += piece.bridge["price_contribution"]
        total += piece.revenue
        segment_revenue[segment.name] = piece.revenue
        notes.extend(piece.notes)
    year = RevenueYear(
        revenue=total,
        bridge={
            "prior_revenue": prior_revenue,
            "growth_rate": None,
            "growth_contribution": total - prior_revenue,
            "volume_contribution": bridges_volume if bridges_volume != 0 else None,
            "price_contribution": bridges_price if bridges_price != 0 else None,
            "segment_contribution": total - prior_revenue,
        },
        segments=segment_revenue,
        notes=notes,
    )
    return year, new_state, ignored


def seed_segment_state(assumptions: Assumptions) -> dict[str, tuple[Decimal, Decimal | None, Decimal | None]]:
    """Base values are applied in the first forecast year, so the seed is empty.

    The first call treats a missing prior as the segment base. Keeping the seed
    empty avoids depreciating the base by one extra year of growth.
    """
    return {}
