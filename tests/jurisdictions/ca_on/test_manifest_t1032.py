"""Form T1032, "Joint Election to Split Pension Income", in the CA-ON manifest: the form `ca/t1032`
and what the return reads of it.

The form runs once (no instances): Step 2 (the maximum split-pension amount, lines 1 to 21), Step
3 (the elected amount, line 22: the amount on line 21000 of the transferring spouse's return or on
line 11600 of the receiving spouse's, as the filer's answer names, checked against line 21), Step 4
(the pension income amounts of line 31400 for both spouses) and Step 5 (the income tax deducted,
lines 35 to 42). The starting inputs are in `01j_t1032_inputs.yaml`, the steps in
`22a_t1032_pension_income_splitting.yaml` and line 33's Note 1 in
`22d_t1032_line_33_note_1.yaml`. The return selects the line 1 check of
`22b_t1032_line_1_check.yaml` (for a transferring spouse's return, line 1 is line 8 of the return's
own Federal Worksheet for line 31400) and reads the form's exports for T1 line 43700 in
`22c_t1032_income_tax_deducted.yaml` and for T1 line 31400 in
`08m_other_federal_non_refundable_credits.yaml`. Lines 37 and 40 of the form are the return's own
`ca/income_tax_deducted`. The entries are listed in
`manifest_families/t1032_pension_income_splitting.py`.
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
from tests.jurisdictions.ca_on.manifest_families import t1032_pension_income_splitting as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01j_t1032_inputs.yaml"
FORM_PART = MANIFESTS / "22a_t1032_pension_income_splitting.yaml"
CHECK_PART = MANIFESTS / "22b_t1032_line_1_check.yaml"
TAX_PART = MANIFESTS / "22c_t1032_income_tax_deducted.yaml"
NOTE_1_PART = MANIFESTS / "22d_t1032_line_33_note_1.yaml"
LINE_31_PART = MANIFESTS / "22e_t1032_line_31_note_1.yaml"
DIED_PART = MANIFESTS / "22f_t1032_transferring_spouse_died.yaml"
ELIGIBILITY_PART = MANIFESTS / "22g_t1032_eligibility.yaml"
NOTE_1_CHECKS_PART = MANIFESTS / "22h_t1032_note_1_checks.yaml"
T1032_PARTS = (
    INPUTS_PART,
    FORM_PART,
    CHECK_PART,
    TAX_PART,
    NOTE_1_PART,
    LINE_31_PART,
    DIED_PART,
    ELIGIBILITY_PART,
    NOTE_1_CHECKS_PART,
)
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
ELECTED_FLAGS = ("ca/elected_split_pension_deduction", "ca/elected_split_pension_amount")


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


def test_the_form_part_declares_the_form_with_no_instances_and_its_exports() -> None:
    declared = yaml.safe_load(FORM_PART.read_text())["form"]

    assert declared == {"name": family.FORM, "required": True, "exports": list(family.EXPORTS)}


def test_the_manifest_has_the_form_with_no_instances_and_its_exports() -> None:
    found = form(family.FORM)

    assert found.instances is None
    assert found.exports == family.EXPORTS


def test_the_form_holds_its_selections_for_lines_1_to_42_and_the_note_1_part() -> None:
    found = form(family.FORM)

    assert len(found.capabilities) == 35 + 16 + 2 + 1 + 4 + 7
    assert set(found.capabilities) == (
        family.FORM_STEPS
        | family.NOTE_1_STEPS
        | family.LINE_31_STEPS
        | family.DIED_STEPS
        | family.ELIGIBILITY_STEPS
        | family.NOTE_1_CHECK_STEPS
    )


def test_the_return_selects_none_of_the_steps_of_the_form() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.FORM_STEPS)


def test_the_return_selects_exactly_the_steps_of_the_checks_and_of_line_43700() -> None:
    (default, *_) = manifest().forms
    selected = {
        each
        for each in default.capabilities
        if "t1032" in " ".join(referenced([*each.consumes.values(), *each.produces.values()]))
    }

    assert selected == family.STEPS


def test_the_line_1_check_part_has_no_form_and_no_outputs_and_selects_eight_steps() -> None:
    declared = yaml.safe_load(CHECK_PART.read_text())

    assert "form" not in declared
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 8


def test_the_line_43700_part_has_no_form_and_no_outputs_and_selects_eight_steps() -> None:
    declared = yaml.safe_load(TAX_PART.read_text())

    assert "form" not in declared
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 8


def test_line_43700_is_line_39_or_line_42_when_the_election_applies_else_as_before() -> None:
    steps = {each.produces["output"]: each for each in family.STEPS}

    assert steps["ca/t1032_line_22_total"].consumes == {"records": "ca/t1032.t1032_line_22_checked"}
    assert steps["ca/t1032_election_applies"].name == "ca/count_by_conditions"
    assert steps["ca/t1032_election_applies"].params == {
        "conditions": "ca/t1032_election_applies_conditions"
    }
    assert steps["ca/t1032_election_applies"].consumes == {
        "counts": (),
        "amounts": ("ca/t1032_line_22_total",),
    }
    assert steps["ca/t1032_line_43700"].consumes == {
        "count": "ca/t1032_filer_is_transferring_spouse_total",
        "when_none": "ca/t1032_line_42_total",
        "when_any": "ca/t1032_line_39_total",
    }
    assert steps["ca/income_tax_deducted_after_election"].consumes == {
        "count": "ca/t1032_election_applies",
        "when_none": "ca/income_tax_deducted",
        "when_any": "ca/t1032_line_43700",
    }


def test_line_31400_is_the_form_s_part_a_or_part_b_amount_when_the_election_applies() -> None:
    steps = {each.produces["output"]: each for each in family.STEPS}

    assert steps["ca/t1032_line_31400_transferring_total"].consumes == {
        "records": "ca/t1032.t1032_line_31400_transferring"
    }
    assert steps["ca/t1032_line_31400_receiving_total"].consumes == {
        "records": "ca/t1032.t1032_line_31400_receiving"
    }
    assert steps["ca/t1032_line_31400"].consumes == {
        "count": "ca/t1032_filer_is_transferring_spouse_total",
        "when_none": "ca/t1032_line_31400_receiving_total",
        "when_any": "ca/t1032_line_31400_transferring_total",
    }
    assert steps["ca/pension_income_credit"].consumes == {
        "count": "ca/t1032_election_applies",
        "when_none": "ca/pension_worksheet_amount",
        "when_any": "ca/t1032_line_31400",
    }


def test_the_pension_split_inputs_and_dataset_are_gone() -> None:
    (default, *_) = manifest().forms
    names = " ".join(
        name
        for each in default.capabilities
        for name in referenced(
            [*each.consumes.values(), *each.produces.values(), *each.params.values()]
        )
    )

    assert "pension_split" not in names
    assert not {"ca/pension_split_election", "ca/pension_split_amount"} & manifest().inputs.keys()


def test_the_total_credits_read_the_income_tax_deducted_after_the_election() -> None:
    (default, *_) = manifest().forms
    (total,) = (
        each for each in default.capabilities if each.produces == {"output": "ca/total_credits"}
    )

    assert "ca/income_tax_deducted_after_election" in total.consumes["parts"]


def test_lines_37_and_40_are_the_return_s_own_income_tax_deducted_not_form_inputs() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert "ca/income_tax_deducted" in manifest().inputs.keys()
    assert "ca/t1032_transferring_spouse_income_tax_deducted" not in declared
    assert "ca/t1032_receiving_spouse_income_tax_deducted" not in declared


def test_the_checked_amounts_of_the_t1032_checks_are_outputs_of_the_outputs_part() -> None:
    assert family.OUTPUTS <= set(manifest().forms[0].exports)


def test_the_line_1_check_refuses_a_line_1_above_and_below_line_8_of_the_worksheet() -> None:
    steps = {each.produces["output"]: each for each in family.STEPS}

    assert steps["ca/t1032_line_1_of_transferring_spouse_checked"].consumes == {
        "amount": "ca/t1032_line_1_of_transferring_spouse",
        "bound": "ca/t1032_worksheet_line_8_of_transferring_spouse",
    }
    assert steps["ca/t1032_worksheet_line_8_of_transferring_spouse_checked"].consumes == {
        "amount": "ca/t1032_worksheet_line_8_of_transferring_spouse",
        "bound": "ca/t1032_line_1_of_transferring_spouse",
    }
    for output, source in (
        ("ca/t1032_line_1_of_transferring_spouse", "ca/t1032_eligible_pension_income"),
        ("ca/t1032_worksheet_line_8_of_transferring_spouse", "ca/pension_chart_line_8"),
    ):
        assert steps[output].name == "core/times_count"
        assert steps[output].consumes == {
            "amount": source,
            "count": "ca/t1032_filer_is_transferring_spouse_total",
        }


def test_the_line_4_check_refuses_a_box_17_above_the_other_income_of_t1_line_13000() -> None:
    steps = {each.produces["output"]: each for each in family.STEPS}

    assert steps["ca/t1032_line_4_of_transferring_spouse_checked"].name == "core/at_most"
    assert steps["ca/t1032_line_4_of_transferring_spouse_checked"].consumes == {
        "amount": "ca/t1032_line_4_of_transferring_spouse",
        "bound": "ca/t1032_other_income_of_transferring_spouse",
    }
    for output, source in (
        ("ca/t1032_line_4_of_transferring_spouse", "ca/t1032_t4a_rca_box_17"),
        ("ca/t1032_other_income_of_transferring_spouse", "ca/other_income"),
    ):
        assert steps[output].name == "core/times_count"
        assert steps[output].consumes == {
            "amount": source,
            "count": "ca/t1032_filer_is_transferring_spouse_total",
        }


def test_the_composed_return_has_the_wiring_of_the_line_1_check() -> None:
    assert family.WIRING <= wiring_of(composed("ca-on/return").composition)


def test_the_t1032_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T1032_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_starting_inputs_of_the_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_line_22_is_one_input_and_the_t1_lines_are_not_inputs() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert "ca/t1032_line_22" in declared
    assert "ca/t1032_filer_is_transferring_spouse" in declared
    assert set(ELECTED_FLAGS).isdisjoint(manifest().inputs.keys())


# --- the selections ------------------------------------------------------------------------------


def test_line_22_is_the_one_input_checked_against_line_21() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    assert selections["ca/t1032_filer_is_transferring_spouse_checked"].name == "ca/yes_or_no_count"
    assert "ca/t1032_line_22_chosen" not in selections
    assert "ca/t1032_elected_amounts_total" not in selections
    assert "ca/t1032_line_22" not in selections
    assert selections["ca/t1032_line_22_checked"].name == "core/at_most"
    assert selections["ca/t1032_line_22_checked"].consumes == {
        "amount": "ca/t1032_line_22",
        "bound": "ca/t1032_line_21_if_conditions_met",
    }
    assert "ca/t1032_larger_elected_amount" not in selections


def test_the_form_exports_its_checked_answer_and_the_line_1_check_reads_it() -> None:
    assert "ca/t1032_filer_is_transferring_spouse_checked" in family.EXPORTS
    (step,) = (
        each
        for each in family.STEPS
        if each.produces["output"] == "ca/t1032_filer_is_transferring_spouse_total"
    )

    assert step.name == "core/first_record_count"
    assert step.consumes == {"records": "ca/t1032.t1032_filer_is_transferring_spouse_checked"}
    assert not any(
        "return_checked" in value
        for each in (*family.STEPS, *family.FORM_STEPS)
        for value in referenced([*each.consumes.values(), *each.produces.values()])
    )


def test_line_21_is_half_of_line_19_at_the_maximum_split_rate() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    assert selections["ca/t1032_line_21"].name == "core/apply_rate"
    assert selections["ca/t1032_line_21"].params == {"rate": "ca/t1032_maximum_split_rate"}
    assert selections["ca/t1032_line_21"].consumes == {"base": "ca/t1032_line_19"}


def test_lines_31400_are_capped_at_the_two_thousand_dollar_pension_income_maximum() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    for output, base in (
        ("ca/t1032_line_31400_transferring", "ca/t1032_line_31_after_note_1"),
        ("ca/t1032_line_31400_receiving", "ca/t1032_line_34"),
    ):
        assert selections[output].name == "core/capped_amount"
        assert selections[output].params == {"cap": "ca/pension_income_maximum"}
        assert selections[output].consumes == {"base": base}


def test_line_18_denominator_is_the_printed_12_or_the_typed_months_if_the_spouse_died() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    assert selections["ca/t1032_line_18_months_in_tax_year"].name == "core/choose_by_count"
    assert selections["ca/t1032_line_18_months_in_tax_year"].consumes == {
        "count": "ca/t1032_transferring_spouse_died_checked",
        "when_none": "ca/t1032_months_in_tax_year_ceiling",
        "when_any": "ca/t1032_months_in_tax_year",
    }
    assert selections["ca/t1032_months_in_tax_year_checked"].name == "core/at_most"
    assert selections["ca/t1032_months_in_tax_year_checked"].consumes == {
        "amount": "ca/t1032_line_18_months_in_tax_year",
        "bound": "ca/t1032_months_in_tax_year_ceiling",
    }
    assert selections["ca/t1032_line_18"].name == "core/apply_ratio"
    assert selections["ca/t1032_line_18"].params == {"rounding": "ca/t1032_rounding"}
    assert selections["ca/t1032_line_18"].consumes == {
        "amount": "ca/t1032_line_17",
        "numerator": "ca/t1032_months_married_checked",
        "denominator": "ca/t1032_months_in_tax_year_checked",
    }


def test_the_ratios_of_lines_29_and_36_are_exact_and_zero_on_a_zero_denominator() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    for output in ("ca/t1032_line_29", "ca/t1032_line_36"):
        assert selections[output].name == "ca/apply_ratio_or_zero", output
        assert selections[output].params == {"rounding": "ca/t1032_rounding"}, output
    assert selections["ca/t1032_line_29"].consumes == {
        "amount": "ca/t1032_line_22_checked",
        "numerator": "ca/t1032_line_8",
        "denominator": "ca/t1032_line_17",
    }
    assert selections["ca/t1032_line_36"].consumes == {
        "amount": "ca/t1032_line_35_checked",
        "numerator": "ca/t1032_line_22_checked",
        "denominator": "ca/t1032_line_17",
    }


def test_line_35_is_refused_above_line_37_for_a_transferring_filer_only() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    for output, source in (
        ("ca/t1032_line_35_of_transferring_spouse", "ca/t1032_income_tax_deducted_on_pension"),
        ("ca/t1032_line_37_of_transferring_spouse", "ca/income_tax_deducted"),
    ):
        assert selections[output].name == "core/times_count"
        assert selections[output].consumes == {
            "amount": source,
            "count": "ca/t1032_filer_is_transferring_spouse_checked",
        }
    assert selections["ca/t1032_line_35_of_transferring_spouse_checked"].consumes == {
        "amount": "ca/t1032_line_35_of_transferring_spouse",
        "bound": "ca/t1032_line_37_of_transferring_spouse",
    }
    assert selections["ca/t1032_line_35_checked"].name == "core/choose_by_count"
    assert selections["ca/t1032_line_35_checked"].consumes == {
        "count": "ca/t1032_filer_is_transferring_spouse_checked",
        "when_none": "ca/t1032_income_tax_deducted_on_pension",
        "when_any": "ca/t1032_line_35_of_transferring_spouse_checked",
    }


def test_the_tax_lines_39_and_42_run_as_printed_from_the_return_s_income_tax_deducted() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    assert selections["ca/t1032_line_39"].consumes == {
        "amount": "ca/income_tax_deducted",
        "less": "ca/t1032_line_36",
    }
    assert selections["ca/t1032_line_42"].consumes == {
        "parts": ("ca/income_tax_deducted", "ca/t1032_line_36")
    }
    assert selections["ca/t1032_line_42"].name == "core/sum"


def test_every_dataset_a_step_reads_is_one_of_the_form_s_datasets() -> None:
    read: set[str] = set()
    for each in (
        *family.FORM_STEPS,
        *family.NOTE_1_STEPS,
        *family.LINE_31_STEPS,
        *family.NOTE_1_CHECK_STEPS,
    ):
        for value in each.params.values():
            read.add(str(value))

    assert read == family.DATASETS | family.NOTE_1_DATASETS
    returns = {str(value) for each in family.STEPS for value in each.params.values()}
    assert returns == family.RETURN_DATASETS


# --- the composed form ---------------------------------------------------------------------------


def test_the_form_runs_once() -> None:
    assert composed(family.FORM).instances is None


def test_the_composed_form_has_the_wiring_of_its_steps() -> None:
    assert family.FORM_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_composed_form_runs_each_line_before_the_lines_that_read_it() -> None:
    order = composed(family.FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert (
        position["ca/t1032_line_2_checked"]
        < position["ca/t1032_line_3"]
        < position["ca/t1032_line_7"]
        < position["ca/t1032_line_8"]
        < position["ca/t1032_line_17"]
        < position["ca/t1032_line_19"]
        < position["ca/t1032_line_21"]
        < position["ca/t1032_line_22_checked"]
        < position["ca/t1032_line_31_after_note_1"]
        < position["ca/t1032_line_31400_transferring"]
    )


# --- line 33 and Note 1 (22d_t1032_line_33_note_1.yaml) ----------------------------------------


def test_the_note_1_part_is_part_of_the_form_and_declares_no_exports() -> None:
    declared = yaml.safe_load(NOTE_1_PART.read_text())

    assert declared["form"] == {"name": family.FORM}
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 16


def test_the_died_part_is_part_of_the_form_and_declares_no_exports() -> None:
    declared = yaml.safe_load(DIED_PART.read_text())

    assert declared["form"] == {"name": family.FORM}
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 1
    assert family.DIED_STEPS <= set(form(family.FORM).capabilities)
    assert family.DIED_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_eligibility_part_is_part_of_the_form_and_declares_no_exports() -> None:
    declared = yaml.safe_load(ELIGIBILITY_PART.read_text())

    assert declared["form"] == {"name": family.FORM}
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 4
    assert family.ELIGIBILITY_STEPS <= set(form(family.FORM).capabilities)
    assert family.ELIGIBILITY_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_form_holds_the_nineteen_selections_of_the_note_1_part() -> None:
    assert family.NOTE_1_STEPS <= set(form(family.FORM).capabilities)


def test_the_note_1_inputs_are_the_four_the_inputs_part_declares() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert {
        "ca/t1032_receiving_spouse_under_65",
        "ca/t1032_transferring_spouse_65_or_older",
        "ca/t1032_note_1_payments_a_to_d",
        "ca/t1032_note_1_payments_due_to_death",
    } <= set(declared)


def test_line_34_adds_line_33_not_line_30_to_line_32() -> None:
    (line_34,) = (
        each
        for each in form(family.FORM).capabilities
        if each.produces == {"output": "ca/t1032_line_34"}
    )

    assert line_34.consumes == {
        "parts": ("ca/t1032_receiving_spouse_pension_amount", "ca/t1032_line_33")
    }


def test_line_33_is_line_30_unless_line_33_is_recalculated() -> None:
    selections = {each.produces["output"]: each for each in family.NOTE_1_STEPS}

    assert selections["ca/t1032_line_33"].consumes == {
        "count": "ca/t1032_note_1_recalculation",
        "when_none": "ca/t1032_line_30",
        "when_any": "ca/t1032_note_1_line_33",
    }
    assert selections["ca/t1032_note_1_recalculation"].consumes == {
        "counts": ("ca/t1032_note_1_applies",),
        "amounts": ("ca/t1032_note_1_result_limit", "ca/t1032_note_1_result"),
    }


def test_only_the_payments_not_received_on_a_death_are_removed_from_line_1() -> None:
    selections = {each.produces["output"]: each for each in family.NOTE_1_STEPS}

    assert selections["ca/t1032_note_1_payments_to_remove"].consumes == {
        "amount": "ca/t1032_note_1_payments_total_if_applies",
        "less": "ca/t1032_note_1_payments_due_to_death_checked",
    }
    assert selections["ca/t1032_note_1_result"].consumes == {
        "amount": "ca/t1032_eligible_pension_income",
        "less": "ca/t1032_note_1_payments_to_remove",
    }


def test_the_recalculation_uses_the_result_as_the_amount_for_line_17() -> None:
    selections = {each.produces["output"]: each for each in family.NOTE_1_STEPS}

    assert selections["ca/t1032_note_1_line_17"].consumes == {
        "count": "ca/t1032_note_1_recalculation",
        "when_none": "ca/t1032_line_17",
        "when_any": "ca/t1032_note_1_result",
    }
    assert selections["ca/t1032_note_1_line_22"].consumes == {
        "amount": "ca/t1032_line_22_checked",
        "bound": "ca/t1032_line_21",
    }
    assert selections["ca/t1032_note_1_line_29"].consumes == {
        "amount": "ca/t1032_note_1_line_22",
        "numerator": "ca/t1032_note_1_line_8_checked",
        "denominator": "ca/t1032_note_1_line_17",
    }
    assert selections["ca/t1032_note_1_line_33"].consumes == {
        "amounts": ("ca/t1032_note_1_line_22", "ca/t1032_note_1_line_30")
    }


def test_the_composed_form_has_the_wiring_of_the_note_1_steps() -> None:
    assert family.NOTE_1_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_composed_form_runs_line_33_before_line_34() -> None:
    composition = composed(family.FORM)
    position = {
        kind.identifier: number
        for number, each in enumerate(composition.composition.order)
        for kind in each.produces
    }

    assert (
        position["ca/t1032_note_1_result"]
        < position["ca/t1032_note_1_line_17"]
        < position["ca/t1032_note_1_line_29"]
        < position["ca/t1032_note_1_line_30"]
        < position["ca/t1032_note_1_line_33"]
        < position["ca/t1032_line_33"]
        < position["ca/t1032_line_34"]
    )


# --- the checks of Note 1 (22h_t1032_note_1_checks.yaml) -----------------------------------------


def test_the_note_1_checks_part_is_part_of_the_form_and_declares_no_exports() -> None:
    declared = yaml.safe_load(NOTE_1_CHECKS_PART.read_text())

    assert declared["form"] == {"name": family.FORM}
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 7
    assert family.NOTE_1_CHECK_STEPS <= set(form(family.FORM).capabilities)


def test_the_payments_count_only_when_note_1_applies() -> None:
    selections = {each.produces["output"]: each for each in family.NOTE_1_CHECK_STEPS}

    assert selections["ca/t1032_note_1_payments_total_if_applies"].consumes == {
        "amount": "ca/t1032_note_1_payments_total",
        "count": "ca/t1032_note_1_applies",
    }
    assert selections["ca/t1032_note_1_payments_due_to_death_if_applies"].consumes == {
        "amount": "ca/t1032_note_1_payments_due_to_death",
        "count": "ca/t1032_note_1_applies",
    }


def test_the_composed_form_has_the_wiring_of_the_note_1_check_steps() -> None:
    assert family.NOTE_1_CHECK_WIRING <= wiring_of(composed(family.FORM).composition)


def test_line_8_is_refused_only_where_the_line_17_of_the_recalculation_is_0() -> None:
    selections = {each.produces["output"]: each for each in family.NOTE_1_CHECK_STEPS}

    assert selections["ca/t1032_note_1_line_8_checked"].consumes == {
        "amount": "ca/t1032_note_1_line_8_to_check",
        "bound": "ca/t1032_note_1_line_8_bound",
    }
    assert selections["ca/t1032_note_1_line_8_bound"].consumes == {
        "count": "ca/t1032_note_1_line_17_is_zero",
        "when_none": "ca/t1032_note_1_line_8_to_check",
        "when_any": "ca/t1032_note_1_line_17",
    }
    assert selections["ca/t1032_note_1_line_8_to_check"].consumes == {
        "amount": "ca/t1032_line_8",
        "count": "ca/t1032_note_1_line_29_applies",
    }


def test_the_composed_form_runs_the_note_1_checks_before_the_lines_that_read_them() -> None:
    composition = composed(family.FORM)
    position = {
        kind.identifier: number
        for number, each in enumerate(composition.composition.order)
        for kind in each.produces
    }

    assert (
        position["ca/t1032_note_1_payments_total_if_applies"]
        < position["ca/t1032_note_1_payments_due_to_death_checked"]
    )
    assert (
        position["ca/t1032_note_1_payments_due_to_death_if_applies"]
        < position["ca/t1032_note_1_payments_due_to_death_checked"]
    )
    assert (
        position["ca/t1032_note_1_line_29_applies"]
        < position["ca/t1032_note_1_line_8_to_check"]
        < position["ca/t1032_note_1_line_8_checked"]
        < position["ca/t1032_note_1_line_29"]
    )


# --- line 31 recalculated (22e_t1032_line_31_note_1.yaml) ---------------------------------------


def test_the_line_31_part_is_part_of_the_form_and_declares_no_exports() -> None:
    declared = yaml.safe_load(LINE_31_PART.read_text())

    assert declared["form"] == {"name": family.FORM}
    assert "outputs" not in declared
    assert len(declared["capabilities"]) == 2
    assert family.LINE_31_STEPS <= set(form(family.FORM).capabilities)


def test_line_31_is_line_1_less_the_recalculated_line_30_when_note_1_recalculates() -> None:
    selections = {each.produces["output"]: each for each in family.LINE_31_STEPS}

    assert selections["ca/t1032_note_1_line_31"].consumes == {
        "amount": "ca/t1032_eligible_pension_income",
        "less": "ca/t1032_note_1_line_30",
    }
    assert selections["ca/t1032_line_31_after_note_1"].consumes == {
        "count": "ca/t1032_note_1_recalculation",
        "when_none": "ca/t1032_line_31",
        "when_any": "ca/t1032_note_1_line_31",
    }


def test_the_composed_form_has_the_wiring_of_the_line_31_steps() -> None:
    assert family.LINE_31_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_composed_form_runs_the_recalculated_line_31_before_line_31400() -> None:
    composition = composed(family.FORM)
    position = {
        kind.identifier: number
        for number, each in enumerate(composition.composition.order)
        for kind in each.produces
    }

    assert (
        position["ca/t1032_note_1_line_30"]
        < position["ca/t1032_note_1_line_31"]
        < position["ca/t1032_line_31_after_note_1"]
        < position["ca/t1032_line_31400_transferring"]
    )
