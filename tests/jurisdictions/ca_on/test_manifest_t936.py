"""Form T936 "Calculation of Cumulative Net Investment Loss (CNIL) to December 31, 2025" in the
CA-ON manifest: the form `ca/t936`, which runs once (no instances), the five amounts it takes, and
the two exports Form T657 reads.

The form is declared in `06j_t936.yaml` (its own steps, one for each printed line that computes),
its copies of the return's steps in `06j_t936_copies.yaml`, its starting inputs in
`01o_t936_inputs.yaml`. The return reads its exports only through the two `core/record_total` steps
of `06b_capital_gains_deduction_t657.yaml` (Form T657 Step 1 line 15 and Step 2 line 16), which this
module lists as the only other part that names the form. The entries of the form are listed in
`manifest_families/t936.py`.
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
from tests.jurisdictions.ca_on.manifest_families import capital_gains_deduction_t657, t2048
from tests.jurisdictions.ca_on.manifest_families import t936 as family
from tests.jurisdictions.ca_on.manifest_support import input_names, inputs_text, lists

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01o_t936_inputs.yaml"
FORM_PART = MANIFESTS / "06j_t936.yaml"
COPIES_PART = MANIFESTS / "06j_t936_copies.yaml"
T657_PART = MANIFESTS / "06b_capital_gains_deduction_t657.yaml"
ALL_INPUTS_PART = MANIFESTS / "01_inputs.yaml"
T936_PARTS = (INPUTS_PART, FORM_PART, COPIES_PART)
# The part that reads the form's exports: the two record totals of Form T657.
READERS = {"06b_capital_gains_deduction_t657.yaml"}
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
# The two amounts Form T657 reads, no longer inputs: Step 1 line 15 and Step 2 line 16.
T657_LINES = {
    "ca/t936.t936_chart_a_line_14": "ca/t657_net_non_eligible_taxable_capital_gains",
    "ca/t936.t936_cnil": "ca/t657_cumulative_net_investment_loss",
}


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
    assert declared["exports"] == list(family.FORM_EXPORTS)


def test_the_copies_part_declares_only_the_form() -> None:
    assert yaml.safe_load(COPIES_PART.read_text())["form"] == {"name": "ca/t936"}


def test_the_manifest_has_the_form_with_no_instances_and_its_two_exports() -> None:
    found = form(family.FORM)

    assert found.instances is None
    assert set(found.exports) == family.EXPORTS
    assert len(found.exports) == 2


def test_the_form_holds_its_own_steps_and_the_copies_of_the_return_steps() -> None:
    found = form(family.FORM)

    assert set(found.capabilities) == family.FORM_STEPS
    assert len(found.capabilities) == len(family.OWN_STEPS) + len(family.COPIED_STEPS)
    assert len(family.OWN_STEPS) == 40
    assert len(family.COPIED_STEPS) == 68


def test_the_copies_are_a_subset_of_the_t2048_copies_verbatim_and_the_schedule_3_sum() -> None:
    schedule_3_line_19900 = {
        step
        for step in family.COPIED_STEPS
        if step.produces == {"output": "ca/schedule_3_line_19900"}
    }

    assert len(schedule_3_line_19900) == 1
    assert family.COPIED_STEPS - schedule_3_line_19900 <= t2048.COPIED_STEPS
    assert len(family.COPIED_STEPS - schedule_3_line_19900) == 67
    # The sum is the step of Form T657 Step 1 line 8, verbatim.
    assert schedule_3_line_19900 <= capital_gains_deduction_t657.STEPS


def test_the_copies_hold_the_steps_the_form_s_figures_need_and_no_other() -> None:
    produced = {step.produces["output"] for step in family.COPIED_STEPS}
    read = referenced(value for step in family.COPIED_STEPS for value in step.consumes.values())

    assert family.COPIED_PRODUCTS_READ <= produced
    # Every copy is read by another copy or by one of the form's own steps.
    own_read = referenced(value for step in family.OWN_STEPS for value in step.consumes.values())
    assert produced <= read | own_read


def test_the_return_selects_none_of_the_own_steps_and_keeps_the_originals_of_the_copies() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.OWN_STEPS)
    assert family.COPIED_STEPS <= selected


def test_only_form_t657_names_the_form_outside_its_own_parts() -> None:
    assert all(part.is_file() for part in T936_PARTS)
    allowed = {path.name for path in T936_PARTS} | READERS
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t936" not in path.read_text(), path.name


def test_the_t936_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T936_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_five_amounts_of_the_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert len(declared) == 5
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_form_s_exports_are_not_inputs_of_the_return() -> None:
    assert family.EXPORTS.isdisjoint(manifest().inputs.keys())
    assert family.EXPORTS.isdisjoint(family.INPUTS)


def test_the_two_t657_amounts_are_no_longer_inputs_of_the_return() -> None:
    inputs = manifest().inputs.keys()
    text = inputs_text()

    for kind in T657_LINES.values():
        assert kind not in inputs, kind
        assert not lists(text, kind), kind
        assert kind not in capital_gains_deduction_t657.INPUTS, kind


def test_the_return_part_of_t657_totals_the_two_exports_into_the_two_t657_amounts() -> None:
    steps = yaml.safe_load(T657_PART.read_text())["capabilities"]
    totals = {
        (step["consumes"]["records"], step["produces"]["output"])
        for step in steps
        if step["name"] == "core/record_total"
        and step["consumes"]["records"].startswith("ca/t936.")
    }

    assert totals == set(T657_LINES.items())


def test_the_t657_family_selects_the_two_record_totals_and_the_return_produces_the_amounts() -> (
    None
):
    selections = {
        (step.consumes["records"], step.produces["output"])
        for step in capital_gains_deduction_t657.STEPS
        if step.name == "core/record_total" and str(step.consumes["records"]).startswith("ca/t936.")
    }

    assert selections == set(T657_LINES.items())
    for amount in T657_LINES.values():
        produced = {
            kind for step in form("ca-on/return").capabilities for kind in step.produces.values()
        }
        assert amount in produced, amount


# --- the selections ------------------------------------------------------------------------------


def test_part_1_line_7_is_the_lesser_of_chart_a_line_20_and_line_25300() -> None:
    line_7 = family.FORM_STEPS_BY_OUTPUT["ca/t936_additional_investment_expenses"]

    assert line_7.name == "core/lesser_of"
    assert set(line_7.consumes["amounts"]) == {
        "ca/t936_additional_investment_income",
        "ca/net_capital_losses_of_other_years",
    }


def test_total_investment_expenses_adds_lines_1_to_7_and_income_adds_lines_8_to_13() -> None:
    expenses = family.FORM_STEPS_BY_OUTPUT["ca/t936_total_investment_expenses"]
    income = family.FORM_STEPS_BY_OUTPUT["ca/t936_total_investment_income"]

    assert expenses.name == income.name == "core/sum"
    assert set(expenses.consumes["parts"]) == {
        "ca/carrying_charges_interest_expenses_and_other_expenses",
        "ca/t936_net_rental_loss",
        "ca/t936_partnership_losses",
        "ca/limited_partnership_losses_of_other_years",
        "ca/t936_exploration_expenses_at_half",
        "ca/t936_other_investment_expenses",
        "ca/t936_additional_investment_expenses",
    }
    assert set(income.consumes["parts"]) == {
        "ca/t936_investment_income",
        "ca/t936_net_rental_income",
        "ca/t936_partnership_income_other_than_gains",
        "ca/t936_other_property_income",
        "ca/t936_recovery_of_exploration_expenses",
        "ca/t936_additional_investment_income",
    }


def test_the_two_50_percent_lines_of_parts_1_and_2_read_their_datasets() -> None:
    expenses = family.FORM_STEPS_BY_OUTPUT["ca/t936_exploration_expenses_at_half"]
    recovery = family.FORM_STEPS_BY_OUTPUT["ca/t936_recovery_of_exploration_expenses"]

    assert expenses.name == recovery.name == "core/apply_rate"
    assert expenses.params == {"rate": "ca/t936_exploration_expenses_rate"}
    assert expenses.consumes == {"base": "ca/exploration_and_development_expenses"}
    assert recovery.params == {"rate": "ca/t936_exploration_recovery_rate"}
    assert recovery.consumes == {"base": "ca/t936_exploration_recovery_income_checked"}
    # The recovery is the input of Form T2048 Chart A line 15, refused above line 13000.
    checked = family.FORM_STEPS_BY_OUTPUT["ca/t936_exploration_recovery_income_checked"]
    assert checked.name == "core/at_most"
    assert checked.consumes == {
        "amount": "ca/qbt_exploration_recovery_income",
        "bound": "ca/other_income",
    }


def test_the_net_rental_loss_and_income_are_the_two_parts_of_the_signed_net_rental_income() -> None:
    income = family.FORM_STEPS_BY_OUTPUT["ca/t936_net_rental_income"]
    loss = family.FORM_STEPS_BY_OUTPUT["ca/t936_net_rental_loss"]

    assert income.name == "core/sum_not_below_zero"
    assert income.consumes == {"parts": ("ca/net_rental_income",)}
    assert loss.name == "core/subtract"
    assert loss.consumes == {"amount": "ca/t936_net_rental_income", "less": "ca/net_rental_income"}


def test_line_10_takes_the_partnership_taxable_capital_gains_off_line_12200_with_no_refusal() -> (
    None
):
    line_10 = family.FORM_STEPS_BY_OUTPUT["ca/t936_partnership_income_other_than_gains"]

    assert line_10.name == "core/subtract"
    assert line_10.consumes == {
        "amount": "ca/net_partnership_income",
        "less": "ca/t936_partnership_taxable_capital_gains",
    }


def test_part_3_line_17_is_the_2024_amount_plus_the_total_of_the_2025_t2048_line_17218() -> None:
    total = family.FORM_STEPS_BY_OUTPUT["ca/t936_t2048_line_17218_for_2025"]
    line_17 = family.FORM_STEPS_BY_OUTPUT["ca/t936_t2048_line_17218"]

    assert total.name == "core/record_total"
    assert total.consumes == {"records": "ca/t2048.qbt_net_investment_loss_reduction"}
    assert line_17.name == "core/sum"
    assert set(line_17.consumes["parts"]) == {
        "ca/t936_t2048_line_17218_for_2024",
        "ca/t936_t2048_line_17218_for_2025",
    }


def test_part_3_lines_14_to_c_follow_the_printed_arithmetic() -> None:
    line_16 = family.FORM_STEPS_BY_OUTPUT["ca/t936_line_16"]
    line_18 = family.FORM_STEPS_BY_OUTPUT["ca/t936_cumulative_investment_expenses"]
    line_21 = family.FORM_STEPS_BY_OUTPUT["ca/t936_cumulative_investment_income"]
    line_c = family.FORM_STEPS_BY_OUTPUT["ca/t936_cnil"]

    # Line 14 is line A and line 19 is line B: no step of their own.
    assert line_16.name == "core/sum"
    assert set(line_16.consumes["parts"]) == {
        "ca/t936_total_investment_expenses",
        "ca/t936_investment_expenses_previous_years",
    }
    # Line 18 prints no floor: signed, `core/subtract`.
    assert line_18.name == "core/subtract"
    assert line_18.consumes == {"amount": "ca/t936_line_16", "less": "ca/t936_t2048_line_17218"}
    assert line_21.name == "core/sum"
    assert set(line_21.consumes["parts"]) == {
        "ca/t936_total_investment_income",
        "ca/t936_investment_income_previous_years",
    }
    # Line C prints "(if negative, enter "0")".
    assert line_c.name == "core/subtract_not_below_zero"
    assert line_c.consumes == {
        "amount": "ca/t936_cumulative_investment_expenses",
        "less": "ca/t936_cumulative_investment_income",
    }


def test_chart_a_lines_2_and_12_total_the_t2048_lines_17215_and_17216() -> None:
    line_2 = family.FORM_STEPS_BY_OUTPUT["ca/t936_t2048_line_17215"]
    line_12 = family.FORM_STEPS_BY_OUTPUT["ca/t936_t2048_line_17216"]

    assert line_2.name == line_12.name == "core/record_total"
    assert line_2.consumes == {"records": "ca/t2048.qbt_taxable_gains_related_to_deduction"}
    assert line_12.consumes == {"records": "ca/t2048.qsbcs_qffp_taxable_gains_related_to_deduction"}


def test_chart_a_line_3_is_signed_and_line_1_is_schedule_3_line_19900_signed() -> None:
    line_3 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_3"]
    line_1 = family.FORM_STEPS_BY_OUTPUT["ca/schedule_3_line_19900"]

    assert line_3.name == "core/subtract"
    assert line_3.consumes == {
        "amount": "ca/schedule_3_line_19900",
        "less": "ca/t936_t2048_line_17215",
    }
    # The signed sum, never the floored `ca/taxable_capital_gains`.
    assert line_1.name == "core/sum"
    assert set(line_1.consumes["parts"]) == {
        "ca/included_capital_gain",
        "ca/partnership_gains_at_full_inclusion",
    }


def test_chart_a_line_7_adds_lines_4_to_6_signed() -> None:
    line_7 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_7"]

    assert line_7.name == "core/sum"
    assert set(line_7.consumes["parts"]) == {
        "ca/qsbcs_gain_or_loss",
        "ca/qffp_gain_or_loss",
        "ca/qffp_foreclosure_gain_or_loss",
    }


def test_chart_a_line_8_is_t2017_line_13_only_when_schedule_3_line_19200_is_not_zero() -> None:
    total = family.FORM_STEPS_BY_OUTPUT["ca/t936_t2017_line_13"]
    positive = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_8_when_positive"]
    negative = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_8_when_negative"]
    line_8 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_8"]

    assert total.name == "core/record_total"
    assert total.consumes == {"records": "ca/t2017.t2017_line_13"}
    # Line 19200 is signed (a reserve of an earlier year brought back is negative): reported when
    # it is more or less than 0. A gate takes one candidate for each branch, so the two branches
    # are two gates and line 8 is their sum.
    for gate, branch in ((positive, "when_positive"), (negative, "when_negative")):
        assert gate.name == "ca/choose_by_sign"
        assert gate.consumes["sign"] == "ca/schedule_3_line_19200"
        assert gate.consumes[branch] == ("ca/t936_t2017_line_13",)
        assert not any(
            gate.consumes[slot]
            for slot in (
                "when_positive",
                "when_zero",
                "when_negative",
                "when_non_positive",
                "when_non_negative",
            )
            if slot != branch
        )
    assert line_8.name == "core/sum"
    assert set(line_8.consumes["parts"]) == {
        "ca/t936_chart_a_line_8_when_positive",
        "ca/t936_chart_a_line_8_when_negative",
    }


def test_chart_a_lines_9_to_13_follow_the_printed_arithmetic() -> None:
    line_9 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_9"]
    product = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_9_at_inclusion_rate"]
    line_11 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_11"]
    line_13 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_13"]

    assert line_9.name == "core/sum"
    assert set(line_9.consumes["parts"]) == {"ca/t936_chart_a_line_7", "ca/t936_chart_a_line_8"}
    assert product.name == "core/apply_rate"
    assert product.params == {"rate": "ca/t936_chart_a_inclusion_rate"}
    assert product.consumes == {"base": "ca/t936_chart_a_line_9"}
    # Line 11 prints "(if negative, enter "0")": the product, not below zero.
    assert line_11.name == "core/sum_not_below_zero"
    assert line_11.consumes == {"parts": ("ca/t936_chart_a_line_9_at_inclusion_rate",)}
    # Line 13 prints no floor: signed, `core/subtract`.
    assert line_13.name == "core/subtract"
    assert line_13.consumes == {
        "amount": "ca/t936_chart_a_line_11",
        "less": "ca/t936_t2048_line_17216",
    }


def test_chart_a_line_14_is_floored_and_zero_when_line_1_is_zero() -> None:
    computed = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_14_before_gate"]
    positive = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_14_when_line_1_positive"]
    negative = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_14_when_line_1_negative"]
    export = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_14"]

    assert computed.name == "core/subtract_not_below_zero"
    assert computed.consumes == {
        "amount": "ca/t936_chart_a_line_3",
        "less": "ca/t936_chart_a_line_13",
    }
    # "If the amount is "0", do not complete lines 2 to 17": the computed line 14 for a positive or
    # negative line 1, else 0: two gates (one candidate for each branch) and the export, their sum.
    for gate, branch in ((positive, "when_positive"), (negative, "when_negative")):
        assert gate.name == "ca/choose_by_sign"
        assert gate.consumes["sign"] == "ca/schedule_3_line_19900"
        assert gate.consumes[branch] == ("ca/t936_chart_a_line_14_before_gate",)
        assert not any(
            gate.consumes[slot]
            for slot in (
                "when_positive",
                "when_zero",
                "when_negative",
                "when_non_positive",
                "when_non_negative",
            )
            if slot != branch
        )
    assert export.name == "core/sum"
    assert set(export.consumes["parts"]) == {
        "ca/t936_chart_a_line_14_when_line_1_positive",
        "ca/t936_chart_a_line_14_when_line_1_negative",
    }


def test_chart_a_lines_15_to_20_follow_the_printed_arithmetic_and_the_line_14_gate() -> None:
    line_17 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_17"]
    product = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_19_before_gate"]
    line_19 = family.FORM_STEPS_BY_OUTPUT["ca/t936_chart_a_line_19"]
    line_20 = family.FORM_STEPS_BY_OUTPUT["ca/t936_additional_investment_income"]

    # Line 17 prints no floor: signed, `core/subtract`.
    assert line_17.name == "core/subtract"
    assert line_17.consumes == {
        "amount": "ca/t936_t3_box_21_capital_gains",
        "less": "ca/t936_t3_box_30_capital_gains",
    }
    assert product.name == "core/apply_rate"
    assert product.params == {"rate": "ca/t936_t3_inclusion_rate"}
    assert product.consumes == {"base": "ca/t936_chart_a_line_17"}
    # "If the total from line 14 is "0", do not complete lines 15 to 19": line 19 is the product
    # only for a line 14 above 0.
    assert line_19.name == "ca/choose_by_sign"
    assert line_19.consumes["sign"] == "ca/t936_chart_a_line_14"
    assert line_19.consumes["when_positive"] == ("ca/t936_chart_a_line_19_before_gate",)
    assert not any(
        line_19.consumes[slot]
        for slot in ("when_zero", "when_negative", "when_non_positive", "when_non_negative")
    )
    # Line 20 prints "(if negative, enter "0")".
    assert line_20.name == "core/subtract_not_below_zero"
    assert line_20.consumes == {
        "amount": "ca/t936_chart_a_line_14",
        "less": "ca/t936_chart_a_line_19",
    }


def test_both_exports_are_produced_by_a_step_of_the_form() -> None:
    produced = {step.produces["output"] for step in family.FORM_STEPS}

    assert family.EXPORTS <= produced


def test_every_input_of_the_form_is_read_by_some_step() -> None:
    read = referenced(value for each in family.FORM_STEPS for value in each.consumes.values())

    assert family.INPUTS <= read


def test_the_form_reads_the_manifest_inputs_and_other_forms_exports_only() -> None:
    produced = {str(k) for step in family.FORM_STEPS for k in step.produces.values()}
    read = referenced(value for step in family.FORM_STEPS for value in step.consumes.values())
    external = read - produced

    assert family.IMPORTS <= external
    # Everything else the form starts from is an input of the return (the five of the form among
    # them), never an artifact the return computes.
    assert external - family.IMPORTS <= manifest().inputs.keys()


# --- the composed form ---------------------------------------------------------------------------


def test_the_composed_form_runs_once() -> None:
    assert composed(family.FORM).instances is None


def test_the_composed_form_imports_the_other_forms_exports_and_derives_its_two() -> None:
    found = composed(family.FORM)

    assert {kind.identifier for kind in found.imports} == family.IMPORTS
    assert {kind.identifier for kind in found.derived} == set(T657_LINES)
    for kind in found.derived:
        assert isinstance(kind, RecordListKind)
        assert len(kind.fields) == 1


def test_the_composed_form_has_the_wiring_of_its_own_steps() -> None:
    assert family.FORM_WIRING <= wiring_of(composed(family.FORM).composition)
    assert len(family.FORM_WIRING) == len(family.OWN_STEPS) == 40


def test_the_composed_form_has_one_capability_for_each_selection() -> None:
    assert len(composed(family.FORM).composition.order) == 108


def test_each_copy_is_wired_as_it_is_on_the_return() -> None:
    inner = {
        kind.identifier: (type(capability), capability.consumes, capability.produces)
        for capability in composed(family.FORM).composition.order
        for kind in capability.produces
    }
    outer = {
        kind.identifier: (type(capability), capability.consumes, capability.produces)
        for capability in build_tax_computation()
        .compose(CA_ON, 2025)
        .form("ca-on/return")
        .composition.order
        for kind in capability.produces
    }
    copied = {step.produces["output"] for step in family.COPIED_STEPS}

    assert copied
    for identifier in copied:
        assert inner[identifier] == outer[identifier], identifier


def test_the_composed_form_runs_the_lines_in_their_printed_order() -> None:
    order = composed(family.FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    # Chart A, then Part 1 line 7 (which reads Chart A line 20), then line A, Part 3 and line C.
    assert (
        position["ca/schedule_3_line_19900"]
        < position["ca/t936_chart_a_line_3"]
        < position["ca/t936_chart_a_line_14_before_gate"]
        < position["ca/t936_chart_a_line_14"]
        < position["ca/t936_chart_a_line_19"]
        < position["ca/t936_additional_investment_income"]
        < position["ca/t936_additional_investment_expenses"]
        < position["ca/t936_total_investment_expenses"]
        < position["ca/t936_line_16"]
        < position["ca/t936_cumulative_investment_expenses"]
        < position["ca/t936_cnil"]
    )
    assert (
        position["ca/t936_additional_investment_income"]
        < position["ca/t936_total_investment_income"]
        < position["ca/t936_cumulative_investment_income"]
        < position["ca/t936_cnil"]
    )
