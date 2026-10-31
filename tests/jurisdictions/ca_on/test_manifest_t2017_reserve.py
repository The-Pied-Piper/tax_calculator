"""Form T2017 (2025), "Summary of Reserves on Dispositions of Capital Property", Part 1 in the CA-ON
manifest: its ten row forms and its summary form, and what the return reads of them.

The part is the ten forms `ca/t2017_line_N_reserve` (N is 2, 3, 4, 8, 9, 10, 17, 21, 24 and 27),
each run once for each record of its list `ca/t2017_line_N_reserve_rows` (the calculation of
reserve), and the summary form `ca/t2017` (run once: the lines of Part 1). The starting inputs
are in
`01j_t2017_inputs.yaml`, each row form in `03z_t2017_line_N_reserve.yaml` and the summary form in
`03z_t2017_summary.yaml`. The entries of the forms are listed in
`manifest_families/t2017_reserve.py`.
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
    T2017_LINE_2_RESERVE_ROWS,
    T2017_LINE_8_RESERVE_ROWS,
    T2017_RESERVE_NINE_YEAR,
    T2017_ROW_RESERVE,
)
from tests.jurisdictions.ca_on.manifest_families import t2017_reserve as family
from tests.jurisdictions.ca_on.manifest_support import (
    input_names,
    instance_fields,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01j_t2017_inputs.yaml"
SUMMARY_PART = MANIFESTS / "03z_t2017_summary.yaml"
ROW_PARTS = {line: MANIFESTS / f"03z_t2017_line_{line}_reserve.yaml" for line in family.ROW_LINES}
T2017_PARTS = (INPUTS_PART, SUMMARY_PART, *ROW_PARTS.values())
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


# --- the parts and the forms ---------------------------------------------------------------------


def test_each_row_part_declares_its_row_form_with_its_list_as_instances_and_the_claim_export() -> (
    None
):
    for line, part in ROW_PARTS.items():
        declared = yaml.safe_load(part.read_text())["form"]

        assert declared == {
            "name": f"ca/t2017_line_{line}_reserve",
            "required": True,
            "fields": required_entries(instance_fields(f"ca/t2017_line_{line}_reserve")),
            "instances": f"ca/t2017_line_{line}_reserve_rows",
            "exports": list(family.row_exports(line)),
        }, part.name


def test_the_summary_part_declares_the_form_with_no_instances_and_its_five_exports() -> None:
    declared = yaml.safe_load(SUMMARY_PART.read_text())["form"]

    assert declared == {
        "name": family.SUMMARY_FORM,
        "required": True,
        "exports": list(family.SUMMARY_EXPORTS),
    }


def test_the_manifest_has_each_row_form_with_its_list_as_instances() -> None:
    for line in family.ROW_LINES:
        found = form(f"ca/t2017_line_{line}_reserve")

        assert found.instances == f"ca/t2017_line_{line}_reserve_rows"
        assert found.exports == family.row_exports(line)


def test_the_manifest_has_the_summary_form_with_no_instances_and_its_exports() -> None:
    found = form(family.SUMMARY_FORM)

    assert found.instances is None
    assert found.exports == family.SUMMARY_EXPORTS


def test_the_return_selects_none_of_the_steps_of_the_forms() -> None:
    selected = set(manifest().forms[0].capabilities)

    for steps in family.ROW_STEPS.values():
        assert selected.isdisjoint(steps)
    assert selected.isdisjoint(family.SUMMARY_STEPS)


def test_no_other_part_of_the_manifest_reads_the_part() -> None:
    # The part of the T657 chart amounts reads the row forms' exports (`04d_...`).
    allowed = {path.name for path in T2017_PARTS} | {"04d_t657_chart_amounts_from_t2017.yaml"}
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t2017_" not in path.read_text(), path.name


def test_the_t2017_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T2017_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_seven_starting_inputs_line_14_and_the_ten_lists() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_line_26_is_computed_from_the_2024_figure_so_the_return_does_not_enter_it() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert "ca/t2017_line_26" not in declared
    assert "ca/t2017_line_26" not in manifest().inputs.keys()
    assert "ca/t2017_lines_66990_and_67058_for_2024" in declared
    assert "ca/t2017_lines_66990_and_67058_for_2024" in manifest().inputs.keys()


def test_line_14_is_an_entered_input_and_no_step_of_the_part_reads_it() -> None:
    assert "ca/t2017_line_14" in manifest().inputs.keys()
    for steps in (*family.ROW_STEPS.values(), family.SUMMARY_STEPS):
        for each in steps:
            assert "ca/t2017_line_14" not in referenced(each.consumes.values()), each.name


def test_the_row_fields_are_the_row_forms_inputs_and_not_the_return_s() -> None:
    assert family.RESERVE_FIELDS.isdisjoint(manifest().inputs.keys())
    assert family.RESERVE_FIELDS.isdisjoint(family.INPUTS)
    assert T2017_RESERVE_NINE_YEAR.identifier not in manifest().inputs.keys()


def test_the_nine_year_answer_is_a_field_of_lines_2_and_8_only() -> None:
    holders = {
        kind.identifier
        for kind in (T2017_LINE_2_RESERVE_ROWS, T2017_LINE_8_RESERVE_ROWS)
        if T2017_RESERVE_NINE_YEAR in kind.fields
    }

    assert holders == {"ca/t2017_line_2_reserve_rows", "ca/t2017_line_8_reserve_rows"}


def test_the_lists_are_record_list_kinds_of_the_row_form_s_fields() -> None:
    for line in family.ROW_LINES:
        kind = family.ROW_LISTS[line]
        assert isinstance(kind, RecordListKind)
        assert kind.identifier in family.INPUTS


# --- the selections ------------------------------------------------------------------------------


def test_each_row_form_reads_only_its_fields_and_what_one_of_its_steps_produces() -> None:
    for line, steps in family.ROW_STEPS.items():
        fields = set(family.RESERVE_FIELDS)
        if line in family.T657_LINES:
            fields |= family.T657_RESERVE_FIELDS
        if line in family.CHOOSING_LINES:
            fields.add("ca/t2017_reserve_nine_year")
        produced = referenced(value for each in steps for value in each.produces.values())
        for each in steps:
            reads = referenced(each.consumes.values())
            assert reads <= fields | produced, (line, each.name)


def test_each_row_form_claims_its_reserve_up_to_the_claim_limit_and_refuses_above_it() -> None:
    for steps in family.ROW_STEPS.values():
        (claim,) = [each for each in steps if each.produces == {"output": "ca/t2017_row_reserve"}]

        assert claim.name == "core/at_most"
        assert claim.consumes == {
            "amount": "ca/t2017_reserve_claimed",
            "bound": "ca/t2017_reserve_claim_limit",
        }


def test_each_row_form_counts_the_later_years_by_the_later_year_conditions() -> None:
    for steps in family.ROW_STEPS.values():
        (count,) = [
            each for each in steps if each.produces == {"output": "ca/t2017_reserve_later_year"}
        ]

        assert count.name == "ca/count_by_conditions"
        assert count.params == {"conditions": "ca/t2017_later_year_conditions"}
        assert tuple(count.consumes["counts"]) == ("ca/t2017_reserve_years_after_disposition",)
        assert tuple(count.consumes["amounts"]) == ()


def test_each_row_form_bounds_a_later_year_by_the_previous_claim_as_well_as_the_maximum() -> None:
    for steps in family.ROW_STEPS.values():
        selections = {each.produces["output"]: each for each in steps}

        later = selections["ca/t2017_reserve_later_year_maximum"]
        assert later.name == "core/lesser_of"
        assert tuple(later.consumes["amounts"]) == (
            "ca/t2017_reserve_maximum",
            "ca/t2017_reserve_previous_year_claim",
        )


def test_each_row_form_limits_the_claim_by_the_maximum_or_the_later_year_maximum() -> None:
    for steps in family.ROW_STEPS.values():
        selections = {each.produces["output"]: each for each in steps}

        limit = selections["ca/t2017_reserve_claim_limit"]
        assert limit.name == "core/choose_by_count"
        assert limit.consumes == {
            "count": "ca/t2017_reserve_later_year",
            "when_none": "ca/t2017_reserve_maximum",
            "when_any": "ca/t2017_reserve_later_year_maximum",
        }


def test_each_row_form_takes_the_lesser_of_the_payment_and_the_percentage_calculations() -> None:
    for steps in family.ROW_STEPS.values():
        selections = {each.produces["output"]: each for each in steps}

        assert selections["ca/t2017_reserve_by_payment"].name == "ca/apply_ratio_or_zero"
        assert selections["ca/t2017_reserve_by_percentage"].name == "ca/apply_percentage"
        assert selections["ca/t2017_reserve_maximum"].name == "core/lesser_of"
        assert tuple(selections["ca/t2017_reserve_maximum"].consumes["amounts"]) == (
            "ca/t2017_reserve_by_payment",
            "ca/t2017_reserve_by_percentage",
        )


def test_lines_3_4_9_10_17_21_and_24_use_the_nine_year_table_only() -> None:
    for line in (3, 4, 9, 10, 17, 21, 24):
        table = [
            each.params["table"]
            for each in family.ROW_STEPS[line]
            if each.name == "core/amount_by_count"
        ]

        assert table == ["ca/t2017_nine_year_percentage"], line


def test_line_27_uses_the_four_year_table_only() -> None:
    table = [
        each.params["table"] for each in family.ROW_STEPS[27] if each.name == "core/amount_by_count"
    ]

    assert table == ["ca/t2017_four_year_percentage"]


def test_lines_2_and_8_choose_between_the_two_tables_by_the_nine_year_answer() -> None:
    for line in (2, 8):
        selections = {each.produces["output"]: each for each in family.ROW_STEPS[line]}

        assert selections["ca/t2017_reserve_nine_year_checked"].name == "ca/yes_or_no_count"
        assert selections["ca/t2017_reserve_nine_year_checked"].consumes == {
            "count": "ca/t2017_reserve_nine_year"
        }
        chosen = selections["ca/t2017_reserve_applicable_percentage"]
        assert chosen.name == "core/choose_by_count"
        assert chosen.consumes == {
            "count": "ca/t2017_reserve_nine_year_checked",
            "when_none": "ca/t2017_reserve_four_year_percentage",
            "when_any": "ca/t2017_reserve_nine_year_percentage",
        }


def test_every_dataset_a_step_reads_is_one_of_the_part_s_datasets() -> None:
    read: set[str] = set()
    for steps in (*family.ROW_STEPS.values(), family.SUMMARY_STEPS):
        for each in steps:
            for value in each.params.values():
                read.add(str(value))

    assert read == family.DATASETS


def test_the_summary_reads_each_row_form_s_total_through_the_record_total_of_its_export() -> None:
    totals = [each for each in family.SUMMARY_STEPS if each.name == "core/record_total"]

    assert len(totals) == len(family.ROW_LINES)
    for each in totals:
        (line,) = [n for n in family.ROW_LINES if each.produces == {"output": f"ca/t2017_line_{n}"}]
        assert each.consumes == {"records": f"ca/t2017_line_{line}_reserve.t2017_row_reserve"}


def test_the_summary_adds_and_subtracts_the_lines_in_the_printed_order() -> None:
    selections = {each.produces["output"]: each for each in family.SUMMARY_STEPS}

    assert selections["ca/t2017_line_5"].name == "core/sum"
    assert tuple(selections["ca/t2017_line_5"].consumes["parts"]) == (
        "ca/t2017_line_2",
        "ca/t2017_line_3",
        "ca/t2017_line_4",
    )
    assert selections["ca/t2017_line_6"].name == "core/subtract"
    assert selections["ca/t2017_line_6"].consumes == {
        "amount": "ca/t2017_line_1",
        "less": "ca/t2017_line_5",
    }
    assert selections["ca/t2017_line_12"].consumes == {
        "amount": "ca/t2017_line_7",
        "less": "ca/t2017_line_11",
    }
    assert selections["ca/t2017_line_26"].name == "core/subtract"
    assert selections["ca/t2017_line_26"].consumes == {
        "amount": "ca/t2017_lines_66990_and_67058_for_2024",
        "less": "ca/t2017_line_23",
    }
    assert selections["ca/t2017_line_26"].produces == {"output": "ca/t2017_line_26"}
    assert tuple(selections["ca/t2017_line_13"].consumes["parts"]) == (
        "ca/t2017_line_6",
        "ca/t2017_line_12",
    )
    assert tuple(selections["ca/t2017_line_29"].consumes["parts"]) == (
        "ca/t2017_line_19",
        "ca/t2017_line_22",
        "ca/t2017_line_25",
        "ca/t2017_line_28",
    )
    assert tuple(selections["ca/t2017_line_31"].consumes["parts"]) == (
        "ca/t2017_line_29",
        "ca/t2017_line_30",
    )


def test_the_summary_steps_run_in_the_order_each_line_is_read() -> None:
    order = composed(family.SUMMARY_FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert (
        position["ca/t2017_line_2"]
        < position["ca/t2017_line_5"]
        < position["ca/t2017_line_6"]
        < position["ca/t2017_line_13"]
        < position["ca/t2017_line_19"]
        < position["ca/t2017_line_29"]
        < position["ca/t2017_line_31"]
    )


# --- the composed forms --------------------------------------------------------------------------


def test_each_row_form_runs_once_for_each_record_of_its_list() -> None:
    for line in family.ROW_LINES:
        found = composed(f"ca/t2017_line_{line}_reserve")

        assert found.instances is not None
        assert found.instances.identifier == f"ca/t2017_line_{line}_reserve_rows"


def test_the_summary_form_runs_once() -> None:
    assert composed(family.SUMMARY_FORM).instances is None


def test_each_composed_row_form_has_the_wiring_of_its_steps() -> None:
    for line in family.ROW_LINES:
        wiring = wiring_of(composed(f"ca/t2017_line_{line}_reserve").composition)

        assert family.ROW_WIRING[line] <= wiring, line


def test_the_composed_summary_form_has_the_wiring_of_its_steps() -> None:
    wiring = wiring_of(composed(family.SUMMARY_FORM).composition)

    assert family.SUMMARY_WIRING <= wiring


def test_the_row_export_is_the_claim_up_to_the_maximum_of_each_row() -> None:
    assert T2017_ROW_RESERVE.identifier == "ca/t2017_row_reserve"
