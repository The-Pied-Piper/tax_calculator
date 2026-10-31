"""Form T1212 "Statement of Deferred Security Options Benefits" in the CA-ON manifest: the form
`ca/t1212`, which runs once (no instances), and the two amounts it takes.

The form is declared in `05y_t1212.yaml`, its starting inputs in `01p_t1212_inputs.yaml`. Its line 3
and the 50% of line 2 of footnote (1) are its steps. The return reads the 50% amount only through
`core/record_total` in `05v_security_options_deduction.yaml`, which this module lists as the only
part that names the form outside its own parts. The entries of the form are listed in
`manifest_families/t1212.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.composition import Composition
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tests.jurisdictions.ca_on.manifest_families import t1212 as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01p_t1212_inputs.yaml"
FORM_PART = MANIFESTS / "05y_t1212.yaml"
T1212_PARTS = (INPUTS_PART, FORM_PART)
# The part that reads the form's export: the security options deduction.
READERS = {"05v_security_options_deduction.yaml"}
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form(name: str) -> Form:
    (found,) = (each for each in manifest().forms if each.name == name)
    return found


def composed(name: str) -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form(name)


def wiring_of(composition: Composition) -> set[tuple[object, object, object]]:
    return {
        (type(capability), capability.consumes, capability.produces)
        for capability in composition.order
    }


def referenced(values: Iterable[object]) -> set[str]:
    """Every identifier named by the values of a selection's slots (a slot may hold a tuple)."""
    names: set[str] = set()
    for value in values:
        if isinstance(value, tuple):
            names |= set(value)
        else:
            names.add(str(value))
    return names


# --- the parts and the form ----------------------------------------------------------------------


def test_the_form_part_declares_the_form_once_with_its_exports() -> None:
    declared = yaml.safe_load(FORM_PART.read_text())["form"]

    assert declared["name"] == family.FORM
    assert "instances" not in declared
    assert set(declared["exports"]) == family.EXPORTS


def test_the_manifest_has_the_form_with_no_instances_and_its_exports() -> None:
    found = form(family.FORM)

    assert found.instances is None
    assert set(found.exports) == family.EXPORTS


def test_the_form_holds_the_selections_of_its_printed_lines() -> None:
    assert set(form(family.FORM).capabilities) == family.FORM_STEPS


def test_the_return_selects_none_of_the_steps_of_the_form() -> None:
    (default, *_) = manifest().forms

    assert set(default.capabilities).isdisjoint(family.FORM_STEPS)


def test_only_the_security_options_deduction_part_names_the_form_outside_its_own_parts() -> None:
    assert all(part.is_file() for part in T1212_PARTS)
    allowed = {path.name for path in T1212_PARTS} | READERS
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t1212" not in path.read_text(), path.name


def test_the_t1212_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T1212_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_two_amounts_of_the_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_old_typed_t691_line_29_amount_is_no_longer_an_input() -> None:
    assert "ca/amt_t1212_line_29_deferred_security_options" not in manifest().inputs.keys()


def test_the_form_s_exports_are_not_inputs_of_the_return() -> None:
    assert family.EXPORTS.isdisjoint(manifest().inputs.keys())
    assert family.EXPORTS.isdisjoint(family.INPUTS)


# --- the selections ------------------------------------------------------------------------------


def test_line_3_subtracts_line_2_from_line_1() -> None:
    (line_3,) = [
        each
        for each in family.FORM_STEPS
        if each.produces == {"output": "ca/t1212_line_3_closing_balance"}
    ]

    assert line_3.name == "core/subtract"
    assert line_3.consumes == {
        "amount": "ca/t1212_line_1_opening_balance",
        "less": "ca/t1212_line_2_benefits_no_longer_deferred",
    }


def test_footnote_1_applies_the_50_percent_rate_to_line_2() -> None:
    (footnote,) = [
        each
        for each in family.FORM_STEPS
        if each.produces == {"output": "ca/t1212_line_24900_amount"}
    ]

    assert footnote.name == "core/apply_rate"
    assert footnote.params == {"rate": "ca/t1212_line_24900_rate"}
    assert footnote.consumes == {"base": "ca/t1212_line_2_benefits_no_longer_deferred"}


def test_every_input_of_the_form_is_read_by_some_step() -> None:
    read = referenced(value for each in family.FORM_STEPS for value in each.consumes.values())

    assert family.INPUTS <= read


# --- the composed form ---------------------------------------------------------------------------


def test_the_composed_form_runs_once() -> None:
    assert composed(family.FORM).instances is None


def test_the_composed_form_has_the_wiring_of_its_steps() -> None:
    assert family.FORM_WIRING <= wiring_of(composed(family.FORM).composition)
