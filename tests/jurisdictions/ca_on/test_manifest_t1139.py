"""Form T1139 "Reconciliation of 2025 Business Income for Tax Purposes" in the CA-ON manifest: the
row form `ca/t1139` (Parts 2 to 5, run once for each business in the list `ca/t1139_businesses`)
and the summary form `ca/t1139_return` (run once: the five income lines of the return).

The forms are declared in `31_t1139.yaml` and `31a_t1139_return.yaml`, their starting list in
`01p_t1139_inputs.yaml`. T1 lines 13500 to 14300 read the summary form's five exports through the
record totals in `03_income.yaml` and the copies of those steps in the parts of Schedule 8, Form
T929 and Form RC381. The entries of the forms are listed in `manifest_families/t1139.py`.
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
from tests.jurisdictions.ca_on.manifest_families import t1139 as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01p_t1139_inputs.yaml"
ROW_PART = MANIFESTS / "31_t1139.yaml"
SUMMARY_PART = MANIFESTS / "31a_t1139_return.yaml"
T1139_PARTS = (INPUTS_PART, ROW_PART, SUMMARY_PART)
# The parts that read the summary form's exports: T1 and the copies of its steps.
READERS = {
    "03_income.yaml",
    "05h_schedule_8_contributions.yaml",
    "05k_t1_m.yaml",
    "05k_t929.yaml",
    "05l_t929_copies_1.yaml",
    "08k_rc381_cpp_limits.yaml",
    "13_refundable_credits.yaml",
}
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
LINES = ("business", "professional", "commission", "farming", "fishing")


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


def test_the_row_part_declares_the_form_over_its_list_with_its_exports() -> None:
    declared = yaml.safe_load(ROW_PART.read_text())["form"]

    assert declared["name"] == family.ROW_FORM
    assert declared["instances"] == family.BUSINESSES_LIST
    assert set(declared["exports"]) == family.ROW_EXPORTS


def test_the_summary_part_declares_the_form_once_with_its_exports() -> None:
    declared = yaml.safe_load(SUMMARY_PART.read_text())["form"]

    assert declared["name"] == family.SUMMARY_FORM
    assert "instances" not in declared
    assert set(declared["exports"]) == family.SUMMARY_EXPORTS


def test_the_manifest_has_both_forms_with_their_instances_and_exports() -> None:
    assert form(family.ROW_FORM).instances == family.BUSINESSES_LIST
    assert set(form(family.ROW_FORM).exports) == family.ROW_EXPORTS
    assert form(family.SUMMARY_FORM).instances is None
    assert set(form(family.SUMMARY_FORM).exports) == family.SUMMARY_EXPORTS


def test_the_forms_hold_the_selections_of_their_printed_lines() -> None:
    assert set(form(family.ROW_FORM).capabilities) == family.ROW_STEPS
    assert set(form(family.SUMMARY_FORM).capabilities) == family.SUMMARY_STEPS


def test_the_return_selects_none_of_the_steps_of_the_forms() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.ROW_STEPS | family.SUMMARY_STEPS)


def test_only_the_income_parts_name_the_summary_form_outside_its_own_parts() -> None:
    assert all(part.is_file() for part in T1139_PARTS)
    allowed = {path.name for path in T1139_PARTS} | READERS
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t1139_return" not in path.read_text(), path.name


def test_the_t1139_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T1139_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_one_list_of_businesses() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_computed_exports_of_the_forms_are_not_inputs_of_the_return() -> None:
    assert (family.ROW_EXPORTS | family.SUMMARY_EXPORTS).isdisjoint(manifest().inputs.keys())


# --- the selections ------------------------------------------------------------------------------


def test_each_line_of_the_return_adds_what_the_forms_report_to_the_statements_left_out() -> None:
    selections = {each.produces["output"]: each for each in family.SUMMARY_STEPS}

    for line in LINES:
        kept = selections[f"ca/t1139_kept_on_{line}_line"]
        on_return = selections[f"ca/t1139_{line}_income_on_return"]
        assert kept.name == "core/subtract"
        assert kept.consumes == {
            "amount": f"ca/t1139_statements_on_{line}_line",
            "less": f"ca/t1139_replaced_total_on_{line}_line",
        }
        assert on_return.name == "core/sum"
        assert set(on_return.consumes["parts"]) == {
            f"ca/t1139_kept_on_{line}_line",
            f"ca/t1139_reported_total_on_{line}_line",
        }


def test_each_line_of_the_return_adds_the_profit_of_the_statements_left_out_and_of_the_forms() -> (
    None
):
    selections = {each.produces["output"]: each for each in family.SUMMARY_STEPS}

    for line in LINES:
        statements = selections[f"ca/t1139_statement_profits_on_{line}_line"]
        replaced = selections[f"ca/t1139_replaced_profits_total_on_{line}_line"]
        kept = selections[f"ca/t1139_kept_profits_on_{line}_line"]
        reported = selections[f"ca/t1139_reported_profits_total_on_{line}_line"]
        on_return = selections[f"ca/t1139_{line}_profit_on_return"]
        assert statements.name == "core/record_positive_total"
        assert replaced.name == "core/record_total"
        assert replaced.consumes == {"records": f"ca/t1139.t1139_profit_replaced_on_{line}_line"}
        assert kept.name == "core/subtract"
        assert kept.consumes == {
            "amount": f"ca/t1139_statement_profits_on_{line}_line",
            "less": f"ca/t1139_replaced_profits_total_on_{line}_line",
        }
        assert reported.name == "core/record_positive_total"
        assert reported.consumes == {"records": f"ca/t1139.t1139_reported_on_{line}_line"}
        assert on_return.name == "core/sum"
        assert set(on_return.consumes["parts"]) == {
            f"ca/t1139_kept_profits_on_{line}_line",
            f"ca/t1139_reported_profits_total_on_{line}_line",
        }


def test_the_profit_readers_read_each_line_through_a_record_total_over_the_summary_export() -> None:
    for name in ("05k_t1_m.yaml", "05k_t929.yaml", "13_refundable_credits.yaml"):
        text = (MANIFESTS / name).read_text()

        for line in LINES:
            assert f"records: ca/t1139_return.t1139_{line}_profit_on_return" in text, (name, line)


def test_t1_reads_each_line_through_a_record_total_over_the_summary_form_export() -> None:
    text = (MANIFESTS / "03_income.yaml").read_text()

    for line in LINES:
        assert f"records: ca/t1139_return.t1139_{line}_income_on_return" in text, line


def test_the_statements_amounts_are_totalled_by_the_capability_that_picks_them_by_position() -> (
    None
):
    names = {each.name for each in family.ROW_STEPS}

    assert "ca/statement_amounts_total" in names


# --- the composed forms --------------------------------------------------------------------------


def test_the_composed_forms_have_the_wiring_of_their_steps() -> None:
    assert family.ROW_WIRING <= wiring_of(composed(family.ROW_FORM).composition)
    assert family.SUMMARY_WIRING <= wiring_of(composed(family.SUMMARY_FORM).composition)


def test_the_composed_row_form_runs_over_the_list_and_the_summary_form_once() -> None:
    assert composed(family.ROW_FORM).instances is not None
    assert composed(family.SUMMARY_FORM).instances is None


def test_the_composed_row_form_runs_the_lines_in_their_printed_order() -> None:
    order = composed(family.ROW_FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert position["ca/t1139_amount_a"] < position["ca/t1139_amount_b"]
    assert position["ca/t1139_amount_b"] < position["ca/t1139_amount_c"]
    assert position["ca/t1139_amount_c"] < position["ca/t1139_amount_d"]
    assert position["ca/t1139_amount_d"] < position["ca/t1139_amount_e"]
    assert position["ca/t1139_amount_e"] < position["ca/t1139_amount_g"]
