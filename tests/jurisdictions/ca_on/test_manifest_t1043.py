"""Form T1043 "Deduction for Excess Registered Pension Plan Transfers You Withdrew from an RRSP, a
PRPP, an SPP, or a RRIF" in the CA-ON manifest: the form `ca/t1043` (lines 1 to 9, run once).

The form is declared in `05z_t1043.yaml`, its starting inputs in `01p_t1043_inputs.yaml`. T1 line
23200 reads the deduction of line 9 through the record total in `05_deductions.yaml`, and the copy
of the line 23300 sum for Form T929 in `05m_t929_copies_2.yaml` reads it through the copy in
`05z_t929_t1043_deduction.yaml`. The entries of the form are listed in
`manifest_families/t1043.py`.
"""

from __future__ import annotations

import re
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
from tests.jurisdictions.ca_on.manifest_families import t1043 as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01p_t1043_inputs.yaml"
FORM_PART = MANIFESTS / "05z_t1043.yaml"
T1043_PARTS = (INPUTS_PART, FORM_PART)
# The parts that read the form's export: the T1 deductions and the copy for Form T929.
READERS = {"05_deductions.yaml", "05m_t929_copies_2.yaml", "05z_t929_t1043_deduction.yaml"}
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


# --- the parts and the form ----------------------------------------------------------------------


def test_the_form_part_declares_the_form_once_with_its_export() -> None:
    declared = yaml.safe_load(FORM_PART.read_text())["form"]

    assert declared["name"] == family.FORM
    assert "instances" not in declared
    assert set(declared["exports"]) == family.EXPORTS


def test_the_manifest_has_the_form_once_with_its_export() -> None:
    assert form(family.FORM).instances is None
    assert set(form(family.FORM).exports) == family.EXPORTS


def test_the_form_holds_the_selections_of_its_printed_lines() -> None:
    assert set(form(family.FORM).capabilities) == family.FORM_STEPS


def test_the_return_selects_none_of_the_steps_of_the_form() -> None:
    (default, *_) = manifest().forms

    assert set(default.capabilities).isdisjoint(family.FORM_STEPS)


def test_only_the_deductions_parts_name_the_form_outside_its_own_parts() -> None:
    assert all(part.is_file() for part in T1043_PARTS)
    allowed = {path.name for path in T1043_PARTS} | READERS
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t1043" not in path.read_text(), path.name


def test_the_t1043_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T1043_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_eight_entries_of_the_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_computed_lines_are_not_inputs_of_the_return() -> None:
    computed = {
        "ca/t1043_excess_transferred",
        "ca/t1043_previously_claimed",
        "ca/t1043_not_yet_claimed",
        "ca/t1043_plan_amounts_remaining",
        "ca/t1043_deduction",
    }

    assert computed.isdisjoint(manifest().inputs.keys())


def test_every_input_of_the_form_is_read_by_some_step() -> None:
    read = {
        name
        for each in family.FORM_STEPS
        for value in each.consumes.values()
        for name in ((value,) if isinstance(value, str) else value)
    }

    assert family.INPUTS <= read


# --- the selections ------------------------------------------------------------------------------


def test_lines_4_and_7_are_refused_above_their_whole_and_not_capped() -> None:
    checks = {
        each.produces["output"]: each for each in family.FORM_STEPS if each.name == "core/at_most"
    }

    assert checks["ca/t1043_previously_claimed_checked"].consumes == {
        "amount": "ca/t1043_previously_claimed",
        "bound": "ca/t1043_excess_transferred",
    }
    assert checks["ca/t1043_part_deductible_elsewhere_checked"].consumes == {
        "amount": "ca/t1043_part_deductible_elsewhere",
        "bound": "ca/t1043_plan_amounts_in_income",
    }


def test_lines_1_and_9_are_each_the_lesser_of_two_amounts() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    for output, amounts in (
        (
            "ca/t1043_excess_transferred",
            {"ca/t1043_excess_transfer_on_t4a", "ca/t1043_excess_amount_on_receipt"},
        ),
        (
            "ca/t1043_line_9",
            {"ca/t1043_not_yet_claimed", "ca/t1043_plan_amounts_remaining"},
        ),
    ):
        assert selections[output].name == "core/lesser_of"
        assert set(selections[output].consumes["amounts"]) == amounts


def test_t1_line_23200_reads_line_9_through_a_record_total_and_both_sums_add_it() -> None:
    reading = (MANIFESTS / "05_deductions.yaml", MANIFESTS / "05z_t929_t1043_deduction.yaml")
    for path in reading:
        assert "records: ca/t1043.t1043_deduction" in path.read_text(), path.name
    for path in (MANIFESTS / "05_deductions.yaml", MANIFESTS / "05m_t929_copies_2.yaml"):
        assert "- ca/t1043_deduction_on_return" in path.read_text(), path.name


def test_the_deduction_is_line_9_times_both_condition_answers() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    for answer in (
        "ca/t1043_included_excess_in_income_for_year_transferred",
        "ca/t1043_including_plan_amounts_in_income_for_year_claimed",
    ):
        assert selections[f"{answer}_checked"].name == "ca/yes_or_no_count"
        assert selections[f"{answer}_checked"].consumes == {"count": answer}
    first = selections["ca/t1043_line_9_if_excess_included"]
    second = selections["ca/t1043_deduction"]
    assert first.name == second.name == "core/times_count"
    assert first.consumes == {
        "amount": "ca/t1043_line_9",
        "count": "ca/t1043_included_excess_in_income_for_year_transferred_checked",
    }
    assert second.consumes == {
        "amount": "ca/t1043_line_9_if_excess_included",
        "count": "ca/t1043_including_plan_amounts_in_income_for_year_claimed_checked",
    }


# --- the composed form ---------------------------------------------------------------------------


def test_the_composed_form_has_the_wiring_of_its_steps() -> None:
    assert family.FORM_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_composed_form_runs_once() -> None:
    assert composed(family.FORM).instances is None


def test_the_composed_form_runs_the_lines_in_their_printed_order() -> None:
    order = composed(family.FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert position["ca/t1043_excess_transferred"] < position["ca/t1043_previously_claimed"]
    assert position["ca/t1043_previously_claimed_checked"] < position["ca/t1043_not_yet_claimed"]
    assert position["ca/t1043_plan_amounts_remaining"] < position["ca/t1043_line_9"]
    assert position["ca/t1043_not_yet_claimed"] < position["ca/t1043_line_9"]
    assert position["ca/t1043_line_9"] < position["ca/t1043_line_9_if_excess_included"]
    assert position["ca/t1043_line_9_if_excess_included"] < position["ca/t1043_deduction"]
