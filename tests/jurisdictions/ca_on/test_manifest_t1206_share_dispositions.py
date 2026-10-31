"""Form T1206 "Dispositions of certain capital property - shares subject to TOSI" in the CA-ON
manifest: its two forms, and what the return reads of them.

The section is the form `ca/t1206_share_dispositions` (no instances, run once: lines A to G, the
under-18 dividend amount and the 18-or-older amount) and the form `ca/t1206_share_reserve` (run once
for each disposition of `ca/t1206_share_reserve_rows`: the calculation of reserve). The starting
inputs are in `01h_t1206_inputs.yaml`, the dispositions form's selections in `03w_t1206_share_
dispositions.yaml` and the reserve form's in `03x_t1206_share_reserve.yaml`. The return reads none
of the exports in this change. The entries of the forms are listed in
`manifest_families/t1206_share_dispositions.py`.
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
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca.catalog import (
    T1206_SHARE_RESERVE_ROWS,
)
from tests.jurisdictions.ca_on.manifest_families import t1206_share_dispositions as family
from tests.jurisdictions.ca_on.manifest_support import (
    input_names,
    instance_fields,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01h_t1206_inputs.yaml"
DISPOSITIONS_PART = MANIFESTS / "03w_t1206_share_dispositions.yaml"
RESERVE_PART = MANIFESTS / "03x_t1206_share_reserve.yaml"
T1206_PARTS = (INPUTS_PART, DISPOSITIONS_PART, RESERVE_PART)
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
AGE_FLAG = "ca/aged_18_or_older_at_end_of_2025"


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


# --- the parts and the forms ---------------------------------------------------------------------


def test_the_dispositions_part_declares_the_form_with_no_instances_and_its_exports() -> None:
    declared = yaml.safe_load(DISPOSITIONS_PART.read_text())["form"]

    assert declared == {
        "name": family.DISPOSITIONS_FORM,
        "required": True,
        "exports": list(family.DISPOSITIONS_EXPORTS),
    }


def test_the_reserve_part_declares_the_form_with_the_rows_as_its_instances_and_its_export() -> None:
    declared = yaml.safe_load(RESERVE_PART.read_text())["form"]

    assert declared == {
        "name": family.RESERVE_FORM,
        "required": True,
        "fields": required_entries(instance_fields(family.RESERVE_FORM)),
        "instances": "ca/t1206_share_reserve_rows",
        "exports": list(family.RESERVE_EXPORTS),
    }


def test_the_manifest_has_the_dispositions_form_with_no_instances_and_its_exports() -> None:
    found = form(family.DISPOSITIONS_FORM)

    assert found.instances is None
    assert found.exports == family.DISPOSITIONS_EXPORTS


def test_the_manifest_has_the_reserve_form_with_the_rows_as_its_instances() -> None:
    found = form(family.RESERVE_FORM)

    assert found.instances == "ca/t1206_share_reserve_rows"
    assert found.exports == family.RESERVE_EXPORTS


def test_the_dispositions_form_holds_its_eleven_selections_for_lines_a_to_g_and_the_amounts() -> (
    None
):
    found = form(family.DISPOSITIONS_FORM)

    assert len(found.capabilities) == 11
    assert set(found.capabilities) == family.DISPOSITIONS_STEPS


def test_the_reserve_form_holds_its_six_selections_for_the_calculation_of_reserve() -> None:
    found = form(family.RESERVE_FORM)

    assert len(found.capabilities) == 6
    assert set(found.capabilities) == family.RESERVE_STEPS


def test_the_return_selects_none_of_the_steps_of_either_form() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.DISPOSITIONS_STEPS)
    assert selected.isdisjoint(family.RESERVE_STEPS)


def test_no_other_part_of_the_manifest_reads_the_section_but_through_its_two_amounts() -> None:
    # The T1 consumers read the exports of the dispositions form, the under-18 dividend amount
    # and the Part 1 line 3 amount, and nothing else of it.
    exports = {f"ca/{name}" for name in family.CONSUMED_EXPORTS}
    allowed = {path.name for path in T1206_PARTS}
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        named = set(re.findall(r"ca/t1206_[a-z0-9_]+", path.read_text()))
        assert named <= exports | {f"{family.DISPOSITIONS_FORM}"}, path.name


def test_the_t1206_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T1206_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_four_starting_inputs_of_the_section() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_age_flag_is_the_return_s_existing_input_and_is_not_declared_again() -> None:
    assert AGE_FLAG in manifest().inputs.keys()
    assert AGE_FLAG not in input_names(yaml.safe_load(INPUTS_PART.read_text()))


def test_the_row_fields_are_the_reserve_form_s_inputs_and_not_the_return_s() -> None:
    assert family.RESERVE_FIELDS.isdisjoint(manifest().inputs.keys())
    assert family.RESERVE_FIELDS.isdisjoint(family.INPUTS)


def test_the_row_fields_hold_the_claim_of_each_disposition_last() -> None:
    fields = [field.identifier for field in T1206_SHARE_RESERVE_ROWS.fields]

    assert fields == [
        "ca/t1206_reserve_capital_gain",
        "ca/t1206_reserve_amount_payable_after_year_end",
        "ca/t1206_reserve_proceeds",
        "ca/t1206_reserve_years_after_sale",
        "ca/t1206_reserve_claimed",
    ]


def test_the_rows_are_the_one_list_input_of_the_reserve_form() -> None:
    assert isinstance(T1206_SHARE_RESERVE_ROWS, RecordListKind)
    assert "ca/t1206_share_reserve_rows" in family.INPUTS


# --- the selections ------------------------------------------------------------------------------


def test_the_dispositions_record_total_reads_the_reserve_copies_export_for_line_c() -> None:
    (total,) = [
        each for each in family.DISPOSITIONS_STEPS if each.produces == {"output": "ca/t1206_line_c"}
    ]

    assert total.name == "core/record_total"
    assert total.consumes == {"records": "ca/t1206_share_reserve.t1206_row_reserve"}


def test_the_dispositions_form_reads_the_age_answer_once_through_a_checked_count() -> None:
    checks = [each for each in family.DISPOSITIONS_STEPS if each.name == "ca/yes_or_no_count"]

    assert len(checks) == 1
    assert checks[0].consumes == {"count": AGE_FLAG}
    assert checks[0].produces == {"output": "ca/t1206_aged_18_or_older_checked"}


def test_line_c_is_checked_against_lines_a_and_b_and_line_d_is_signed_from_line_b() -> None:
    selections = {each.produces["output"]: each for each in family.DISPOSITIONS_STEPS}

    assert selections["ca/t1206_line_c_checked"].name == "core/at_most"
    assert selections["ca/t1206_line_c_checked"].consumes == {
        "amount": "ca/t1206_line_c",
        "bound": "ca/t1206_lines_a_and_b",
    }
    assert selections["ca/t1206_line_d"].name == "core/subtract"
    assert selections["ca/t1206_line_d"].consumes == {
        "amount": "ca/t1206_reserve_2024",
        "less": "ca/t1206_line_c_checked",
    }


def test_lines_e_and_g_are_sums_of_the_form_s_lines() -> None:
    selections = {each.produces["output"]: each for each in family.DISPOSITIONS_STEPS}

    assert selections["ca/t1206_line_e"].name == "core/sum"
    assert tuple(selections["ca/t1206_line_e"].consumes["parts"]) == (
        "ca/t1206_capital_gain_on_dispositions",
        "ca/t1206_line_d",
    )
    assert selections["ca/t1206_line_g"].name == "core/sum"
    assert tuple(selections["ca/t1206_line_g"].consumes["parts"]) == (
        "ca/t1206_line_e",
        "ca/t1206_t3_box_21_capital_gains",
    )


def test_the_two_branches_read_line_g_and_the_age_percentages_of_their_datasets() -> None:
    selections = {each.produces["output"]: each for each in family.DISPOSITIONS_STEPS}

    assert selections["ca/t1206_under_18_dividend_amount"].consumes == {
        "amount": "ca/t1206_line_g",
        "percentage": "ca/t1206_under_18_percent",
    }
    assert selections["ca/t1206_part_1_line_3_amount"].consumes == {
        "amount": "ca/t1206_line_g",
        "percentage": "ca/t1206_part_1_line_3_percent",
    }
    assert selections["ca/t1206_under_18_percent"].params == {
        "table": "ca/t1206_under_18_percentage"
    }
    assert selections["ca/t1206_part_1_line_3_percent"].params == {
        "table": "ca/t1206_aged_18_or_older_percentage"
    }


def test_the_reserve_form_reads_only_its_row_fields_and_what_one_of_its_steps_produces() -> None:
    produced = referenced(
        value for each in family.RESERVE_STEPS for value in each.produces.values()
    )
    for each in family.RESERVE_STEPS:
        reads = referenced(each.consumes.values())
        assert reads <= family.RESERVE_FIELDS | produced, each.name


def test_the_reserve_steps_run_as_the_printed_calculation() -> None:
    selections = {each.produces["output"]: each for each in family.RESERVE_STEPS}

    assert selections["ca/t1206_reserve_payable_checked"].name == "core/at_most"
    assert selections["ca/t1206_reserve_by_payment"].name == "ca/apply_ratio_or_zero"
    assert selections["ca/t1206_reserve_applicable_percentage"].params == {
        "table": "ca/t1206_reserve_percentage"
    }
    assert selections["ca/t1206_reserve_by_percentage"].name == "ca/apply_percentage"
    assert selections["ca/t1206_reserve_maximum"].name == "core/lesser_of"
    assert tuple(selections["ca/t1206_reserve_maximum"].consumes["amounts"]) == (
        "ca/t1206_reserve_by_payment",
        "ca/t1206_reserve_by_percentage",
    )
    assert selections["ca/t1206_row_reserve"].name == "core/at_most"
    assert selections["ca/t1206_row_reserve"].consumes == {
        "amount": "ca/t1206_reserve_claimed",
        "bound": "ca/t1206_reserve_maximum",
    }


def test_every_dataset_a_step_reads_is_one_of_the_section_s_datasets() -> None:
    read: set[str] = set()
    for each in (*family.DISPOSITIONS_STEPS, *family.RESERVE_STEPS):
        for value in each.params.values():
            read.add(str(value))

    assert read == family.DATASETS


# --- the composed forms --------------------------------------------------------------------------


def test_the_dispositions_form_runs_once() -> None:
    assert composed(family.DISPOSITIONS_FORM).instances is None


def test_the_reserve_form_runs_once_for_each_row_of_the_list() -> None:
    found = composed(family.RESERVE_FORM)

    assert found.instances is not None
    assert found.instances.identifier == "ca/t1206_share_reserve_rows"


def test_the_composed_dispositions_form_has_the_wiring_of_its_steps() -> None:
    assert family.DISPOSITIONS_WIRING <= wiring_of(composed(family.DISPOSITIONS_FORM).composition)


def test_the_composed_reserve_form_has_the_wiring_of_its_steps() -> None:
    assert family.RESERVE_WIRING <= wiring_of(composed(family.RESERVE_FORM).composition)


def test_the_composed_dispositions_form_runs_line_c_before_the_lines_that_read_it() -> None:
    order = composed(family.DISPOSITIONS_FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert (
        position["ca/t1206_line_c"]
        < position["ca/t1206_line_c_checked"]
        < position["ca/t1206_line_d"]
        < position["ca/t1206_line_e"]
        < position["ca/t1206_line_g"]
        < position["ca/t1206_under_18_dividend_amount"]
    )
