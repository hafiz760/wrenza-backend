"""Recursive snake_case → camelCase for handlers that return raw dicts.

Most responses go through `CamelModel`, which handles this via its alias
generator. A handful of admin routers build plain dicts instead; wrapping those
in `camelize` keeps the whole API on one convention, so clients never have to
remember which endpoints are the odd ones out.
"""

from typing import Any


def to_camel(key: str) -> str:
    head, *tail = key.split("_")
    return head + "".join(word.capitalize() for word in tail)


def camelize(value: Any) -> Any:
    if isinstance(value, dict):
        return {to_camel(k): camelize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [camelize(item) for item in value]
    return value
