"""Rebuild a company model from the JSON snapshot stored by the API.

Decimal amounts are accepted as strings or integers. Floats are refused so a
JSON number such as 0.1 cannot enter the engine through binary rounding.
"""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Union, get_args, get_origin, get_type_hints

from financial_engine.model import CompanyModel
from financial_engine.precision import D

_HINTS: dict[type, dict[str, Any]] = {}


def _hints(cls: type) -> dict[str, Any]:
    cached = _HINTS.get(cls)
    if cached is None:
        cached = get_type_hints(cls)
        _HINTS[cls] = cached
    return cached


def hydrate(annotation: Any, data: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = get_args(annotation)
        if data is None and type(None) in args:
            return None
        concrete = [arg for arg in args if arg is not type(None)]
        if len(concrete) == 1:
            return hydrate(concrete[0], data)
        return data
    if data is None:
        return None
    if annotation is Any or annotation is object:
        return data
    if annotation is Decimal:
        return D(data)
    if annotation is date:
        return date.fromisoformat(data) if isinstance(data, str) else data
    if annotation is int and not isinstance(data, bool):
        return int(data)
    if annotation is bool:
        if not isinstance(data, bool):
            raise TypeError("Expected a boolean.")
        return data
    if annotation is str:
        return str(data)
    if origin is list:
        (item_type,) = get_args(annotation) or (Any,)
        return [hydrate(item_type, item) for item in data]
    if origin is dict:
        args = get_args(annotation)
        value_type = args[1] if len(args) == 2 else Any
        return {str(key): hydrate(value_type, value) for key, value in data.items()}
    if origin is tuple:
        args = get_args(annotation)
        return tuple(hydrate(args[index] if index < len(args) else Any, part) for index, part in enumerate(data))
    if get_origin(annotation) is None and is_dataclass(annotation):
        hints = _hints(annotation)
        kwargs = {}
        for field in fields(annotation):
            if field.name in data:
                kwargs[field.name] = hydrate(hints[field.name], data[field.name])
        return annotation(**kwargs)
    return data


def model_from_dict(data: dict[str, Any]) -> CompanyModel:
    model = hydrate(CompanyModel, data)
    if not isinstance(model, CompanyModel):
        raise TypeError("Snapshot did not decode to a company model.")
    return model
