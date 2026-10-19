"""The stored snapshot must rebuild the same model the engine saved."""

from financial_engine.codec import model_from_dict
from financial_engine.reference.northline import northline_model
from financial_engine.serialize import to_jsonable


def test_snapshot_round_trip_preserves_inputs():
    original = northline_model()
    original.historical[0].income["personnel"] = None
    encoded = to_jsonable(original)
    restored = model_from_dict(encoded)
    assert to_jsonable(restored) == encoded
    assert restored.historical[0].income["personnel"] is None
    assert restored.assumptions.growth_rates["2025"] == original.assumptions.growth_rates["2025"]
    assert restored.assumptions.wacc.market_value_equity == original.assumptions.wacc.market_value_equity
