"""Test support: manifest inputs declared the way the manifest declares them."""

from __future__ import annotations

from collections.abc import Iterable

from tax_engine.domain.manifest import InputDeclaration
from tax_engine.domain.record_list import RecordListKind


def required_fields(kind: RecordListKind) -> tuple[InputDeclaration, ...]:
    """A required declaration for each field of `kind`, in the kind's order."""
    return tuple(InputDeclaration(name=field.identifier, required=True) for field in kind.fields)


def required_inputs(names: Iterable[str]) -> dict[str, InputDeclaration]:
    """A required declaration for each of `names`, by identifier."""
    return {name: InputDeclaration(name=name, required=True) for name in sorted(names)}
