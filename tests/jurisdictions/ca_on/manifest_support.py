"""Helpers shared by the manifest tests, for the shape of the YAML parts.

A part's `inputs:` entries are mappings (`name`, `required`), and the `form:` block of the part
that declares `exports:` also says `required: true`, with a `fields:` list of the same shape when
the form has `instances:`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations  # noqa: F401
from tax_engine import build_tax_computation
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.record_list import RecordListKind


def input_names(document: dict[str, Any]) -> list[str]:
    """The identifiers of the `inputs:` entries of a loaded part, in order."""
    return [entry["name"] for entry in document["inputs"]]


def required_entries(names: Iterable[str]) -> list[dict[str, Any]]:
    """The `- name: x` / `required: true` entries for these names."""
    return [{"name": name, "required": True} for name in names]


def declared_form(name: str, fields: Iterable[str] | None = None, **rest: Any) -> dict[str, Any]:
    """The `form:` block of the part that declares `exports:`, as the manifest now spells it."""
    declared: dict[str, Any] = {"name": name, "required": True, **rest}
    if fields is not None:
        declared["fields"] = required_entries(fields)
    return declared


def instance_fields(form_name: str) -> list[str]:
    """The identifiers of the fields of the record list a form takes as instances, in order.

    The manifest declares each of them under the form's `fields:`.
    """
    instances = (
        build_tax_computation().compose(JurisdictionCode("CA-ON"), 2025).form(form_name).instances
    )
    assert isinstance(instances, RecordListKind)
    return [kind.identifier for kind in instances.fields]


def form_with_instances(name: str, **rest: Any) -> dict[str, Any]:
    """`declared_form` for a form with `instances:`, with the fields of that list."""
    return declared_form(name, instance_fields(name), **rest)


def lists(text: str, identifier: str, *, indent: str = "") -> bool:
    """Whether the YAML text has the identifier as a list entry, bare or as `name:` of a mapping."""
    return f"{indent}- {identifier}\n" in text or f"{indent}- name: {identifier}\n" in text


MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
# The return's own inputs: the part `01_inputs.yaml` is split in two to stay under 30 KB.
INPUTS_PARTS = (MANIFESTS / "01_inputs.yaml", MANIFESTS / "01q_inputs_continued.yaml")


def inputs_text() -> str:
    """The text of both parts that hold the return's own inputs."""
    return "".join(part.read_text() for part in INPUTS_PARTS)


def all_input_names() -> list[str]:
    """The identifiers of the `inputs:` entries of both parts that hold the return's own inputs."""
    return [name for part in INPUTS_PARTS for name in input_names(yaml.safe_load(part.read_text()))]


def capabilities_of(*parts: Path) -> list[dict[str, Any]]:
    """The `capabilities:` of the parts of one form, in order (a big part is split in two)."""
    return [step for part in parts for step in yaml.safe_load(part.read_text())["capabilities"]]
