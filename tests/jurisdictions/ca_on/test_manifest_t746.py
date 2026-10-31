"""Form T746 "Calculating Your Deduction for Refund of Unused RRSP, PRPP, and SPP Contributions" in
the CA-ON manifest: the row form `ca/t746_year` (lines 1 to 4, run once for each year listed) and
the summary form `ca/t746` (lines 4 to 13, run once).

The forms are declared in `05y_t746_year.yaml` and `05y_t746.yaml`, their starting inputs in
`01o_t746_inputs.yaml`. T1 line 23200 reads the deduction of line 13 through the record total in
`05_deductions.yaml`, and the copy of the line 23300 sum for Form T929 in `05m_t929_copies_2.yaml`
reads it through the copy in `05y_t929_t746_deduction.yaml`. The entries of the forms are listed
in `manifest_families/t746.py`.
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
from tests.jurisdictions.ca_on.manifest_families import t746 as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01o_t746_inputs.yaml"
YEAR_PART = MANIFESTS / "05y_t746_year.yaml"
SUMMARY_PART = MANIFESTS / "05y_t746.yaml"
T746_PARTS = (INPUTS_PART, YEAR_PART, SUMMARY_PART)
# The parts that read the summary form's export: the T1 deductions and the copy for Form T929.
READERS = {"05_deductions.yaml", "05m_t929_copies_2.yaml", "05y_t929_t746_deduction.yaml"}
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


# --- the parts and the forms ---------------------------------------------------------------------


def test_the_year_part_declares_the_row_form_over_its_list_with_its_exports() -> None:
    declared = yaml.safe_load(YEAR_PART.read_text())["form"]

    assert declared["name"] == family.YEAR_FORM
    assert declared["instances"] == family.YEARS_LIST
    assert set(declared["exports"]) == family.YEAR_EXPORTS


def test_the_summary_part_declares_the_form_once_with_its_exports() -> None:
    declared = yaml.safe_load(SUMMARY_PART.read_text())["form"]

    assert declared["name"] == family.SUMMARY_FORM
    assert "instances" not in declared
    assert set(declared["exports"]) == family.SUMMARY_EXPORTS


def test_the_manifest_has_both_forms_with_their_instances_and_exports() -> None:
    assert form(family.YEAR_FORM).instances == family.YEARS_LIST
    assert set(form(family.YEAR_FORM).exports) == family.YEAR_EXPORTS
    assert form(family.SUMMARY_FORM).instances is None
    assert set(form(family.SUMMARY_FORM).exports) == family.SUMMARY_EXPORTS


def test_the_forms_hold_the_selections_of_their_printed_lines() -> None:
    assert set(form(family.YEAR_FORM).capabilities) == family.YEAR_STEPS
    assert set(form(family.SUMMARY_FORM).capabilities) == family.SUMMARY_STEPS


def test_the_return_selects_none_of_the_steps_of_the_forms() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.YEAR_STEPS | family.SUMMARY_STEPS)


def test_only_the_deductions_parts_name_the_summary_form_outside_its_own_parts() -> None:
    assert all(part.is_file() for part in T746_PARTS)
    allowed = {path.name for path in T746_PARTS} | READERS
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t746" not in path.read_text(), path.name


def test_the_t746_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T746_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_list_and_the_six_entries_of_the_summary_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_row_fields_are_the_row_form_s_inputs_and_not_the_return_s() -> None:
    row_fields = {
        "ca/t746_contribution_year",
        "ca/t746_contributions",
        "ca/t746_contributions_deducted",
    }

    assert row_fields.isdisjoint(manifest().inputs.keys())
    assert row_fields.isdisjoint(family.INPUTS)


def test_line_5_is_an_entered_input_and_no_step_reads_it() -> None:
    steps = family.YEAR_STEPS | family.SUMMARY_STEPS
    read = {
        name
        for each in steps
        for value in each.consumes.values()
        for name in ((value,) if isinstance(value, str) else value)
    }

    assert "ca/t746_withdrawal_year" in manifest().inputs.keys()
    assert "ca/t746_withdrawal_year" not in read
    assert "ca/t746_contribution_year" not in read


def test_the_computed_exports_of_the_forms_are_not_inputs_of_the_return() -> None:
    computed = {"ca/t746_unused_contributions_of_year", "ca/t746_deduction"}
    assert computed.isdisjoint(manifest().inputs.keys())


# --- the selections ------------------------------------------------------------------------------


def test_line_3_is_refused_above_line_2_and_not_capped() -> None:
    (checked,) = [
        each
        for each in family.YEAR_STEPS
        if each.produces == {"output": "ca/t746_contributions_deducted_checked"}
    ]

    assert checked.name == "core/at_most"
    assert checked.consumes == {
        "amount": "ca/t746_contributions_deducted",
        "bound": "ca/t746_contributions",
    }


def test_line_12_adds_lines_6_to_10_and_line_13_is_the_lesser_of_lines_4_and_12() -> None:
    selections = {each.produces["output"]: each for each in family.SUMMARY_STEPS}

    assert selections["ca/t746_withdrawals"].name == "core/sum"
    assert set(selections["ca/t746_withdrawals"].consumes["parts"]) == {
        "ca/t746_t4rsp_box_20",
        "ca/t746_t4rsp_box_22",
        "ca/t746_t4rif_box_24",
        "ca/t746_t4a_box_194",
        "ca/t746_t4a_box_18_spp",
    }
    assert selections["ca/t746_line_13"].name == "core/lesser_of"
    assert set(selections["ca/t746_line_13"].consumes["amounts"]) == {
        "ca/t746_unused_contributions",
        "ca/t746_withdrawals",
    }


def test_the_deduction_is_line_13_when_one_or_both_conditions_are_yes() -> None:
    selections = {each.produces["output"]: each for each in family.SUMMARY_STEPS}

    assert selections["ca/t746_conditions_met"].name == "ca/count_by_conditions"
    assert selections["ca/t746_conditions_met"].params == {"conditions": "ca/t746_conditions"}
    assert selections["ca/t746_deduction"].name == "core/times_count"
    assert selections["ca/t746_deduction"].consumes == {
        "amount": "ca/t746_line_13",
        "count": "ca/t746_conditions_met",
    }


def test_t1_line_23200_reads_line_13_through_a_record_total_and_both_sums_add_it() -> None:
    reading = (MANIFESTS / "05_deductions.yaml", MANIFESTS / "05y_t929_t746_deduction.yaml")
    for path in reading:
        assert "records: ca/t746.t746_deduction" in path.read_text(), path.name
    for path in (MANIFESTS / "05_deductions.yaml", MANIFESTS / "05m_t929_copies_2.yaml"):
        assert "- ca/t746_deduction_on_return" in path.read_text(), path.name


def test_every_entry_of_the_summary_form_is_read_by_some_step() -> None:
    read = {
        name
        for each in family.SUMMARY_STEPS
        for value in each.consumes.values()
        for name in ((value,) if isinstance(value, str) else value)
    }

    assert family.SUMMARY_INPUTS - {"ca/t746_withdrawal_year"} <= read


# --- the composed forms --------------------------------------------------------------------------


def test_the_composed_forms_have_the_wiring_of_their_steps() -> None:
    assert family.YEAR_WIRING <= wiring_of(composed(family.YEAR_FORM).composition)
    assert family.SUMMARY_WIRING <= wiring_of(composed(family.SUMMARY_FORM).composition)


def test_the_composed_row_form_runs_over_the_list_and_the_summary_form_once() -> None:
    assert composed(family.YEAR_FORM).instances is not None
    assert composed(family.SUMMARY_FORM).instances is None


def test_the_composed_summary_form_runs_the_lines_in_their_printed_order() -> None:
    order = composed(family.SUMMARY_FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert position["ca/t746_unused_contributions"] < position["ca/t746_deduction"]
    assert position["ca/t746_withdrawals"] < position["ca/t746_deduction"]
