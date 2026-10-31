"""Form T90 "Income Exempt from Tax under the Indian Act" in the CA-ON manifest: the form `ca/t90`,
which runs once (no instances), and the sixteen amounts it takes.

The form is declared in `12d_t90.yaml`, its starting inputs in `01j_t90_inputs.yaml`. Its lines 4,
14, 16, 18 and 20 and the check of line 10019 are its steps. The return reads its exports only
through the Schedule 6 steps of `12_canada_workers_benefit.yaml` and `12c_cwb_spouse_column.yaml`,
which `test_manifest_t90.py` lists as the only parts that name the form. The entries of the form
are listed in `manifest_families/t90.py`.
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
from tests.jurisdictions.ca_on.manifest_families import t90 as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01j_t90_inputs.yaml"
FORM_PART = MANIFESTS / "12d_t90.yaml"
T90_PARTS = (INPUTS_PART, FORM_PART)
# The parts that read the form's exports: the Schedule 6 parts of the Canada workers benefit.
READERS = {
    "12_canada_workers_benefit.yaml",
    "12c_cwb_spouse_column.yaml",
}
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
    found = form(family.FORM)

    assert set(found.capabilities) == family.FORM_STEPS


def test_the_return_selects_none_of_the_steps_of_the_form() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.FORM_STEPS)


def test_only_the_schedule_6_parts_name_the_form_outside_its_own_parts() -> None:
    assert all(part.is_file() for part in T90_PARTS)
    allowed = {path.name for path in T90_PARTS} | READERS
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t90" not in path.read_text(), path.name


def test_the_t90_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T90_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_sixteen_amounts_of_the_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_form_s_exports_are_not_inputs_of_the_return() -> None:
    assert family.EXPORTS.isdisjoint(manifest().inputs.keys())
    assert family.EXPORTS.isdisjoint(family.INPUTS)


# --- the selections ------------------------------------------------------------------------------


def test_line_4_is_the_sum_of_lines_1_to_3_and_is_exported() -> None:
    (line_4,) = [
        each
        for each in family.FORM_STEPS
        if each.produces == {"output": "ca/t90_exempt_working_income"}
    ]

    assert line_4.name == "core/sum"
    assert set(line_4.consumes["parts"]) == {
        "ca/t90_t4_box_71_employment_income",
        "ca/t90_other_employment_income",
        "ca/t90_net_self_employment_income",
    }


def test_line_10019_is_refused_above_line_9_and_is_not_capped() -> None:
    (checked,) = [
        each
        for each in family.FORM_STEPS
        if each.produces == {"output": "ca/t90_ei_maternity_parental_ppip_benefits_checked"}
    ]

    assert checked.name == "core/at_most"
    assert checked.consumes == {
        "amount": "ca/t90_ei_maternity_parental_ppip_benefits",
        "bound": "ca/t90_ei_ppip_and_other_benefits",
    }


def test_line_14_adds_line_4_and_lines_5_to_13_but_not_line_10019() -> None:
    (line_14,) = [
        each for each in family.FORM_STEPS if each.produces == {"output": "ca/t90_line_14"}
    ]

    assert line_14.name == "core/sum"
    parts = set(line_14.consumes["parts"])
    assert "ca/t90_exempt_working_income" in parts
    assert "ca/t90_ei_maternity_parental_ppip_benefits" not in parts
    assert "ca/t90_ei_ppip_and_other_benefits" in parts
    assert "ca/t90_net_rental_losses" not in parts
    assert "ca/t90_net_self_employment_losses" not in parts
    assert "ca/t90_deductions_relating_to_exempt_income" not in parts


def test_lines_16_18_and_20_subtract_the_losses_and_the_deductions_in_turn() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    assert selections["ca/t90_line_16"].name == "core/subtract"
    assert selections["ca/t90_line_16"].consumes == {
        "amount": "ca/t90_line_14",
        "less": "ca/t90_net_rental_losses",
    }
    assert selections["ca/t90_total_exempt_income"].name == "core/subtract"
    assert selections["ca/t90_total_exempt_income"].consumes == {
        "amount": "ca/t90_line_16",
        "less": "ca/t90_net_self_employment_losses",
    }
    assert selections["ca/t90_net_exempt_income"].name == "core/subtract"
    assert selections["ca/t90_net_exempt_income"].consumes == {
        "amount": "ca/t90_total_exempt_income",
        "less": "ca/t90_deductions_relating_to_exempt_income",
    }


def test_every_input_of_the_form_is_read_by_some_step() -> None:
    read = referenced(value for each in family.FORM_STEPS for value in each.consumes.values())

    assert family.INPUTS <= read


# --- the composed form ---------------------------------------------------------------------------


def test_the_composed_form_runs_once() -> None:
    assert composed(family.FORM).instances is None


def test_the_composed_form_has_the_wiring_of_its_steps() -> None:
    assert family.FORM_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_composed_form_runs_the_lines_in_their_printed_order() -> None:
    order = composed(family.FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert (
        position["ca/t90_exempt_working_income"]
        < position["ca/t90_line_14"]
        < position["ca/t90_line_16"]
        < position["ca/t90_total_exempt_income"]
        < position["ca/t90_net_exempt_income"]
    )
