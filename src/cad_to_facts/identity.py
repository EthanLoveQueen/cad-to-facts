from collections.abc import Mapping
from typing import Any

import hashlib
import rfc8785
from pydantic import BaseModel

SCHEMA_VERSION = "0.1"


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_json_bytes(value: BaseModel | Mapping[str, Any], *, exclude: set[str] | None = None) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude=exclude or set(), exclude_none=True)
    return rfc8785.dumps(_json_value(value))


def structured_hash(
    object_type: str,
    value: BaseModel | Mapping[str, Any],
    *,
    schema_version: str = SCHEMA_VERSION,
    exclude: set[str] | None = None,
) -> str:
    prefix = f"cad-to-facts:{object_type}:{schema_version}\0".encode("utf-8")
    return hashlib.sha256(prefix + canonical_json_bytes(value, exclude=exclude)).hexdigest()
