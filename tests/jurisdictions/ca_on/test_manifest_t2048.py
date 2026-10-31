"""Form T2048 in the CA-ON manifest: one instance for each disposition, and what the return reads.

T2048 is the form `ca/t2048`, run once for each disposition of the record list
`ca/t2048_dispositions`, whose fields are the 9 T2048 inputs (`FORM_INPUTS`). Its limit is
`min_instances` 0 and no maximum: any number of dispositions is accepted. The form's selections are
`FORM_STEPS`: its 54 own (`OWN_STEPS`) and 69 copies of the return's steps that compute the 11
figures it reads (`COPIED_STEPS`; the return keeps the originals). The form exports the nine
artifacts of `TOTALED_EXPORTS` and a tenth, the order check's; the return re-produces each of the
nine with `core/record_total` over the form's derived kind `ca/t2048.<name>` (`STEPS`), so every
consumer keeps its name and its figure, and with no disposition every one of them is 0. The form
reads the manifest inputs, its record fields, the other form's export `IMPORTS` and its own earlier
runs (`EARLIER`): notes (1) to (3) subtract the sum of the earlier runs' lines 32, 41 and 42 from
lines 8, 23 and Chart A line 20, and a QBT listed after a QCC is an input error. The entries are
listed in `manifest_families/t2048.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.inbound.trace_english import EnglishTraceRenderer
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.artifact import ArtifactRegistry
from tax_engine.domain.errors import InputAboveBoundError, ValidationError
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tax_engine.domain.record_list import RecordListKind
from tax_engine.domain.trace.forms import FormInstanceLine
from tax_engine.domain.worksheet import Worksheet
from tax_engine.jurisdictions.ca.catalog import (
    ALLOWABLE_BUSINESS_INVESTMENT_LOSS,
    QBT_ABIL_REDUCTION,
    QBT_ALLOCATION_TOTAL,
    QBT_ALLOWABLE_BUSINESS_INVESTMENT_LOSS_AFTER_EARLIER,
    QBT_AMOUNT_ALLOCATED,
    QBT_CAPITAL_GAINS_DEDUCTION,
    QBT_CHART_A_NET_INVESTMENT_LOSS,
    QBT_CHART_A_NET_INVESTMENT_LOSS_AFTER_EARLIER,
    QBT_DEDUCTION_AVAILABLE,
    QBT_EARLIER_ABIL_REDUCTION_TOTAL,
    QBT_EARLIER_ALLOCATION_TOTAL,
    QBT_EARLIER_NET_INVESTMENT_LOSS_REDUCTION_TOTAL,
    QBT_ELECTION_DEDUCTION,
    QBT_ELECTION_ELIGIBLE_AMOUNT_CHECKED,
    QBT_ELECTION_IS_QBT_IN_ORDER,
    QBT_HAS_INVESTMENT_EXPENSES,
    QBT_INVESTMENT_INCOME,
    QBT_MAXIMUM_DEDUCTION,
    QBT_NET_INVESTMENT_LOSS,
    QBT_NET_INVESTMENT_LOSS_REDUCTION,
    QBT_PARTNERSHIP_INCOME_OTHER_THAN_GAINS,
    QBT_PERCENTAGE_ALLOCATED_CHECKED,
    QBT_TAXABLE_CAPITAL_GAINS,
    QBT_TAXABLE_CAPITAL_GAINS_AFTER_EARLIER,
    QBT_TAXABLE_GAINS_LIMIT,
    QBT_TAXABLE_GAINS_NOT_LIMITED,
    QBT_TAXABLE_GAINS_RELATED_TO_DEDUCTION,
    QBT_TOTAL_CAPITAL_GAINS,
    QCC_ELECTION_DEDUCTION,
    QSBCS_QFFP_TAXABLE_GAINS_RELATED_TO_DEDUCTION,
    T2048_DISPOSITIONS,
    TAXABLE_CAPITAL_GAINS,
)
from tests.jurisdictions.ca_on.end_to_end.support import D, run, service
from tests.jurisdictions.ca_on.manifest_families import t2048
from tests.jurisdictions.ca_on.manifest_support import (
    inputs_text,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
ROOTS = tax_engine.registrations.JURISDICTIONS.roots()
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "06a_capital_gains_deduction_qbt.yaml"
)
COPIES_PART = PART.with_name("06a_capital_gains_deduction_qbt_copies.yaml")
T1436_PART = PART.with_name("06a_t1436_lines_1_to_7_t2048.yaml")
LINE_1_PART = PART.with_name("06a_t2048_part_2_line_1_maximum.yaml")
INCOME_PART = PART.with_name("06_taxable_income.yaml")
# Chart A line 15's input is declared in a part of its own: 01_inputs.yaml is at its size cap.
RECOVERY_INPUT_PART = PART.with_name("01o_exploration_recovery_income.yaml")
VALUED_EXPORTS = (
    QBT_ALLOCATION_TOTAL,
    QCC_ELECTION_DEDUCTION,
    QBT_ELECTION_DEDUCTION,
    QBT_TAXABLE_CAPITAL_GAINS,
    QBT_TAXABLE_GAINS_RELATED_TO_DEDUCTION,
    QSBCS_QFFP_TAXABLE_GAINS_RELATED_TO_DEDUCTION,
    QBT_ABIL_REDUCTION,
    QBT_NET_INVESTMENT_LOSS_REDUCTION,
    QBT_CAPITAL_GAINS_DEDUCTION,
)


def manifest() -> Manifest:
    (only,) = YamlJurisdictionSource(ROOTS).get_jurisdiction(CA_ON).manifests
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/t2048")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t2048")


# --- the parts and the form ----------------------------------------------------------------------


def test_the_t2048_part_declares_the_form_ca_t2048_with_its_instances_minimum_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    # No `max_instances`: any number of dispositions is accepted.
    assert declared == {
        "name": "ca/t2048",
        "required": True,
        "fields": required_entries(instance_fields("ca/t2048")),
        "instances": "ca/t2048_dispositions",
        "min_instances": 0,
        "exports": list(t2048.FORM_EXPORTS),
    }
    assert len(t2048.FORM_EXPORTS) == 10


def test_the_t2048_copies_part_declares_only_the_form_ca_t2048() -> None:
    assert yaml.safe_load(COPIES_PART.read_text())["form"] == {"name": "ca/t2048"}


def test_the_t1436_lines_1_to_7_part_declares_only_the_form_ca_t2048() -> None:
    # The T1436 lines 1 to 7 and the Schedule 3 sum of lines 2 and 3 moved out of the copies part.
    assert yaml.safe_load(T1436_PART.read_text())["form"] == {"name": "ca/t2048"}
    assert T1436_PART.stat().st_size <= 30 * 1024


def test_the_line_1_maximum_part_declares_only_the_form_ca_t2048() -> None:
    assert yaml.safe_load(LINE_1_PART.read_text())["form"] == {"name": "ca/t2048"}
    assert LINE_1_PART.stat().st_size <= 30 * 1024


def test_the_t2048_parts_are_not_over_30_kb() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert COPIES_PART.stat().st_size <= 30 * 1024


def test_the_other_parts_hold_no_t2048_input_and_the_dispositions_input_is_declared() -> None:
    inputs_text_ = inputs_text() + RECOVERY_INPUT_PART.read_text()

    for identifier in t2048.INPUTS:
        assert f"- name: {identifier}\n" in inputs_text_, identifier
    for identifier in t2048.FORM_INPUTS:
        assert not lists(inputs_text_, identifier), identifier
        assert not lists(INCOME_PART.read_text(), identifier), identifier


def test_the_return_part_holds_the_nine_record_totals_of_the_form_exports() -> None:
    steps = yaml.safe_load(INCOME_PART.read_text())["capabilities"]
    totals = {
        (step["consumes"]["records"], step["produces"]["output"])
        for step in steps
        if step["name"] == "core/record_total"
        and step["consumes"]["records"].startswith("ca/t2048.")
    }

    assert totals == {(step.consumes["records"], step.produces["output"]) for step in t2048.STEPS}
    assert len(totals) == len(t2048.TOTALED_EXPORTS) == 9


# --- the form and the return ---------------------------------------------------------------------


def test_the_manifest_has_the_form_t2048_for_each_disposition_with_no_maximum() -> None:
    found = form()

    assert found.name == "ca/t2048"
    assert found.instances == "ca/t2048_dispositions"
    assert found.exports == t2048.FORM_EXPORTS
    assert found.min_instances == 0
    assert found.max_instances is None
    assert found.exclusive_group is None


def test_the_form_holds_the_54_own_selections_and_69_copies_of_the_return_steps() -> None:
    found = form()

    assert len(found.capabilities) == 123
    assert set(found.capabilities) == t2048.FORM_STEPS
    assert len(t2048.OWN_STEPS) == 54
    assert len(t2048.COPIED_STEPS) == 69
    assert t2048.FORM_STEPS == t2048.OWN_STEPS | t2048.COPIED_STEPS


def test_the_return_selects_one_record_total_for_each_export_and_none_of_the_form_steps() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t2048.STEPS <= selected
    # The return keeps the 69 steps the form copies (its own originals), and none of its 34 own.
    assert t2048.COPIED_STEPS <= selected
    assert not selected & t2048.OWN_STEPS
    assert {step.name for step in t2048.STEPS} == {"core/record_total"}
    assert len(t2048.STEPS) == len(t2048.TOTALED_EXPORTS) == 9


def test_the_return_declares_the_outputs_it_reads_or_outputs_and_not_the_claim() -> None:
    (default, *_) = manifest().forms

    assert t2048.OUTPUTS <= set(default.exports)
    assert len(t2048.OUTPUTS) == 8
    # Line 25395 is read by the return (taxable income, the foreign tax credit and the AMT) but is
    # no output of it: the return re-produces it, and declares no export for it.
    assert QBT_CAPITAL_GAINS_DEDUCTION.identifier not in default.exports


# --- the instances input -------------------------------------------------------------------------


def test_the_dispositions_are_the_one_input_of_the_manifest_in_place_of_the_t2048_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert t2048.INPUTS <= inputs
    assert inputs.isdisjoint(t2048.FORM_INPUTS)


def test_the_dispositions_kind_is_registered_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert isinstance(T2048_DISPOSITIONS, RecordListKind)
    assert ArtifactRegistry.shared().kind("ca/t2048_dispositions") is T2048_DISPOSITIONS


def test_the_dispositions_kind_has_the_nine_inputs_and_no_nested_list() -> None:
    identifiers = [field.identifier for field in T2048_DISPOSITIONS.fields]

    assert frozenset(identifiers) == t2048.FORM_INPUTS
    assert len(identifiers) == len(t2048.FORM_INPUTS) == 9
    assert not [field for field in T2048_DISPOSITIONS.fields if isinstance(field, RecordListKind)]


# --- the form's run ------------------------------------------------------------------------------


def test_the_form_runs_once_per_disposition_on_its_selections_and_derives_its_ten_kinds() -> None:
    found = composed()

    assert found.instances == T2048_DISPOSITIONS
    assert {kind.identifier for kind in found.imports} == t2048.IMPORTS
    assert len(found.derived) == 10
    assert {kind.identifier for kind in found.derived} == {
        "ca/t2048." + export.split("/", 1)[1] for export in t2048.FORM_EXPORTS
    }


def test_each_derived_kind_is_a_record_list_of_the_export_it_names() -> None:
    by_name = {kind.identifier: kind for kind in composed().derived}

    for export in t2048.FORM_EXPORTS:
        derived = by_name["ca/t2048." + export.split("/", 1)[1]]
        assert isinstance(derived, RecordListKind)
        assert len(derived.fields) == 1
        assert derived.fields[0].identifier == export


def test_the_form_selections_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t2048.FORM_WIRING
    assert len(composed().composition.order) == 123
    assert len(t2048.FORM_WIRING) == 123


def test_the_form_reads_four_of_its_own_derived_kinds_the_earlier_runs() -> None:
    # Line 32, line 41 and line 42 (notes (1) to (3)) and the election answers (the order check).
    assert {kind.identifier for kind in composed().earlier} == t2048.EARLIER
    assert len(t2048.EARLIER) == 4


def test_the_form_reads_its_fields_the_other_export_its_earlier_runs_and_shared_inputs_only() -> (
    None
):
    produced = {str(k) for step in t2048.FORM_STEPS for k in step.produces.values()}
    read: set[str] = set()
    for step in t2048.FORM_STEPS:
        for value in step.consumes.values():
            read |= set(value) if isinstance(value, (tuple, list)) else {value}
    external = read - produced
    # The copies read the return's shared inputs (manifest inputs), the 9 fields and the one
    # export of another form; the notes and the order check read the form's own earlier runs;
    # nothing else comes from outside the form.
    assert t2048.FORM_INPUTS <= external
    assert t2048.IMPORTS <= external
    assert t2048.EARLIER <= external
    assert external - t2048.FORM_INPUTS - t2048.IMPORTS - t2048.EARLIER <= manifest().inputs.keys()


def test_the_return_wiring_is_nine_record_totals_over_the_form_derived_kinds() -> None:
    assert len(t2048.WIRING) == 9
    assert {wiring[0].__name__ for wiring in t2048.WIRING} == {"RecordTotal"}


# --- the limits and the figures ------------------------------------------------------------------


def test_two_dispositions_are_accepted_and_the_form_runs_once_for_each() -> None:
    runs = run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=({}, {}))

    assert len(runs["ca/t2048"]) == 2


def test_any_number_of_dispositions_is_accepted() -> None:
    runs = run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=({},) * 5)

    assert len(runs["ca/t2048"]) == 5


def test_with_zero_dispositions_every_exported_total_is_zero() -> None:
    runs = run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=())
    worksheet = runs["ca-on/return"][0]

    assert runs.get("ca/t2048", ()) == ()
    for kind in VALUED_EXPORTS:
        assert worksheet.get(kind).value == D("0"), kind.identifier


def test_the_form_run_is_a_form_instance_line_whose_lines_read_ca_t2048_instance_1() -> None:
    runs = run(
        "0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=({"qbt_capital_gains": "100000"},)
    )
    (line,) = [
        each
        for each in service().compose(CA_ON, 2025).trace(runs)
        if isinstance(each, FormInstanceLine) and each.form == "ca/t2048"
    ]

    assert line.position == 1
    assert line.lines == runs["ca/t2048"][0].trace
    (text,) = EnglishTraceRenderer().render_all((line,))
    assert text.split("\n")
    assert all(sentence.startswith("ca/t2048, instance 1: ") for sentence in text.split("\n"))


# --- the percentage allocated: refused above 100 (a choice, the form prints no maximum) --------

# The dollar example: a total eligible amount of 100,000 and capital gains of 100,000. At 100% the
# whole 100,000 is allocated (line 3) and the deduction available is half of it (line 7).
DOLLARS: dict[str, str | int] = {
    "qbt_election_eligible_amount": "100000",
    "qbt_percentage_allocated": "100",
    "qbt_capital_gains": "100000",
    "qbt_election_is_qbt": 1,
    "qbt_deduction_claimed": "0",
}


def test_the_percentage_is_checked_before_the_apply_step_of_the_part() -> None:
    # Line 2 is checked against the 100% maximum before line 3 multiplies by it (the T2125 Area G
    # pattern: `core/credit_amount`, then `core/at_most`, then `ca/apply_percentage`).
    steps = yaml.safe_load(PART.read_text())["capabilities"]

    assert steps[:3] == [
        {
            "name": "core/credit_amount",
            "params": {"amount": "ca/qbt_percentage_allocated_maximum"},
            "produces": {"output": "ca/qbt_percentage_allocated_maximum"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/qbt_percentage_allocated",
                "bound": "ca/qbt_percentage_allocated_maximum",
            },
            "produces": {"output": "ca/qbt_percentage_allocated_checked"},
        },
        {
            "name": "ca/apply_percentage",
            "params": {"rounding": "ca/qbt_amount_allocated_rounding"},
            "consumes": {
                "amount": "ca/qbt_election_eligible_amount_checked",
                "percentage": "ca/qbt_percentage_allocated_checked",
            },
            "produces": {"output": "ca/qbt_amount_allocated"},
        },
    ]


def test_the_eligible_amount_is_checked_by_the_line_1_part_before_line_3_reads_it() -> None:
    # Line 1 is checked against its printed $10 million maximum (`core/credit_amount`, then
    # `core/at_most`, in the part of its own); line 3 reads the checked amount.
    assert yaml.safe_load(LINE_1_PART.read_text())["capabilities"] == [
        {
            "name": "core/credit_amount",
            "params": {"amount": "ca/qbt_election_eligible_amount_maximum"},
            "produces": {"output": "ca/qbt_election_eligible_amount_maximum"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/qbt_election_eligible_amount",
                "bound": "ca/qbt_election_eligible_amount_maximum",
            },
            "produces": {"output": "ca/qbt_election_eligible_amount_checked"},
        },
    ]


@pytest.mark.parametrize("amount", ["0", "9999999.99", "10000000"])
def test_an_eligible_amount_of_0_or_up_to_10_million_is_accepted(amount: str) -> None:
    (one,) = run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        t2048_dispositions_rows=({"qbt_election_eligible_amount": amount},),
    )["ca/t2048"]

    assert one.get(QBT_ELECTION_ELIGIBLE_AMOUNT_CHECKED).value == D(amount)


@pytest.mark.parametrize("amount", ["10000000.01", "15000000"])
def test_an_eligible_amount_above_10_million_is_an_input_error_not_a_cap(amount: str) -> None:
    # The form prints the maximum: 15,000,000 is refused and not capped to 10,000,000.
    with pytest.raises(InputAboveBoundError) as raised:
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=({"qbt_election_eligible_amount": amount},),
        )

    assert str(raised.value) == (
        f"ca/t2048, instance 1: ca/qbt_election_eligible_amount {amount} is above "
        "ca/qbt_election_eligible_amount_maximum 10000000.00"
    )


def test_the_second_of_two_dispositions_above_10_million_is_refused_as_instance_2() -> None:
    with pytest.raises(InputAboveBoundError) as raised:
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=(
                {"qbt_election_eligible_amount": "10000000"},
                {"qbt_election_eligible_amount": "15000000"},
            ),
        )

    assert str(raised.value) == (
        "ca/t2048, instance 2: ca/qbt_election_eligible_amount 15000000 is above "
        "ca/qbt_election_eligible_amount_maximum 10000000.00"
    )


def test_the_dollar_example_allocates_half_of_10_million_and_refuses_15_million() -> None:
    # At the maximum of 10,000,000 and a 50% share, line 3 is 5,000,000.00; 15,000,000 is refused.
    rows = {**DOLLARS, "qbt_election_eligible_amount": "10000000", "qbt_percentage_allocated": "50"}
    (one,) = run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=(rows,))["ca/t2048"]

    assert one.get(QBT_AMOUNT_ALLOCATED).value == D("5000000.00")
    with pytest.raises(InputAboveBoundError):
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=({**rows, "qbt_election_eligible_amount": "15000000"},),
        )


@pytest.mark.parametrize("percentage", ["0", "100"])
def test_a_percentage_allocated_of_0_or_100_is_accepted(percentage: str) -> None:
    (one,) = run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        t2048_dispositions_rows=({"qbt_percentage_allocated": percentage},),
    )["ca/t2048"]

    assert one.get(QBT_PERCENTAGE_ALLOCATED_CHECKED).value == D(percentage)


@pytest.mark.parametrize("percentage", ["100.01", "150"])
def test_a_percentage_allocated_above_100_is_an_input_error_not_a_cap(percentage: str) -> None:
    # The form prints no maximum: the refusal is a choice, so 150 is refused and not capped to 100.
    with pytest.raises(InputAboveBoundError) as raised:
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=({"qbt_percentage_allocated": percentage},),
        )

    assert str(raised.value) == (
        f"ca/t2048, instance 1: ca/qbt_percentage_allocated {percentage} is above "
        "ca/qbt_percentage_allocated_maximum 100.00"
    )


def test_the_second_of_two_dispositions_above_100_is_refused_as_instance_2() -> None:
    with pytest.raises(InputAboveBoundError) as raised:
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=(
                {"qbt_percentage_allocated": "100"},
                {"qbt_percentage_allocated": "150"},
            ),
        )

    assert str(raised.value) == (
        "ca/t2048, instance 2: ca/qbt_percentage_allocated 150 is above "
        "ca/qbt_percentage_allocated_maximum 100.00"
    )


def test_the_dollar_example_allocates_the_whole_election_at_100_and_refuses_150() -> None:
    (one,) = run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=(DOLLARS,))["ca/t2048"]

    assert one.get(QBT_AMOUNT_ALLOCATED).value == D("100000.00")
    assert one.get(QBT_DEDUCTION_AVAILABLE).value == D("50000.00")
    with pytest.raises(InputAboveBoundError):
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=({**DOLLARS, "qbt_percentage_allocated": "150"},),
        )


# --- notes (1) to (3): the earlier runs' lines 32, 41 and 42 ----------------------------------

# A return with taxable capital gains (line 12700) of 100,000.00, a business investment loss of
# 8,000 (ABIL 4,000.00, line 21700) and carrying charges of 5,000. Each disposition is a QBT:
# line 1 600,000 at 50% (line 7 is 150,000.00), gains of 160,000 (line 16 is 80,000.00) and 30,000
# of other investment expenses (Chart A line 6), with investment expenses in 2025. The first claims
# 40,000; the others claim 0.
QBT: dict[str, str | int] = {
    "qbt_election_eligible_amount": "600000",
    "qbt_percentage_allocated": "50",
    "qbt_capital_gains": "160000",
    "qbt_election_is_qbt": 1,
}


def scenario(rows: tuple[dict[str, str | int], ...]) -> dict[str, tuple[Worksheet, ...]]:
    return run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        slip_capital_gains_or_losses="200000",
        business_investment_loss="8000",
        total_carrying_charges="5000",
        other_investment_expenses="30000",
        has_investment_expenses=1,
        t2048_dispositions_rows=rows,
    )


def qbts(*claims: str) -> list[Worksheet]:
    rows = tuple({**QBT, "qbt_deduction_claimed": claim} for claim in claims)
    return list(scenario(rows)["ca/t2048"])


def test_the_first_run_has_no_earlier_amount_so_its_lines_are_the_returns() -> None:
    # No earlier run: the sums of all previous amounts are 0, line 8 is line 12700 (100,000.00),
    # line 23 is the ABIL (4,000.00) and Chart A line 20 is 15,000.00: line 10 is 5,000 + 30,000 =
    # 35,000.00 and line 19 is line 18 (100,000.00 - 80,000.00 = 20,000.00), 35,000.00 - 20,000.00.
    (first,) = qbts("40000")

    assert first.get(QBT_EARLIER_ALLOCATION_TOTAL).value == D("0")
    assert first.get(QBT_EARLIER_ABIL_REDUCTION_TOTAL).value == D("0")
    assert first.get(QBT_EARLIER_NET_INVESTMENT_LOSS_REDUCTION_TOTAL).value == D("0")
    assert first.get(QBT_TAXABLE_CAPITAL_GAINS_AFTER_EARLIER).value == D("100000.00")
    assert first.get(QBT_ALLOWABLE_BUSINESS_INVESTMENT_LOSS_AFTER_EARLIER).value == D("4000.00")
    assert first.get(QBT_CHART_A_NET_INVESTMENT_LOSS_AFTER_EARLIER).value == D("15000.00")
    assert first.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("15000.00")


def test_the_first_run_of_several_is_as_it_would_be_alone() -> None:
    # Line 17 is 80,000.00; line 25 is 0 + 4,000.00 + 15,000.00 = 19,000.00; line 26 is 61,000.00;
    # 40,000 is claimed. Line 30 is 80,000.00 - 40,000 = 40,000.00 and line 32 is 80,000.00. Line
    # 35 is 19,000.00; line 36 is the lesser of 40,000.00 and 19,000.00; line 41 is 4,000.00 and
    # line 42 is 15,000.00.
    first, *_ = qbts("40000", "0")

    assert first.get(QBT_ALLOCATION_TOTAL).value == D("80000.00")
    assert first.get(QBT_ABIL_REDUCTION).value == D("4000.00")
    assert first.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D("15000.00")


def test_note_1_takes_the_earlier_line_32_from_line_8() -> None:
    # Note (1): line 8 of the next form is 100,000.00 - 80,000.00 (the first form's line 32) =
    # 20,000.00, so its line 17 is the lesser of that and its line 16 (80,000.00): 20,000.00.
    first, second = qbts("40000", "0")

    assert second.get(QBT_EARLIER_ALLOCATION_TOTAL).value == first.get(QBT_ALLOCATION_TOTAL).value
    assert second.get(QBT_EARLIER_ALLOCATION_TOTAL).value == D("80000.00")
    assert second.get(QBT_TAXABLE_CAPITAL_GAINS_AFTER_EARLIER).value == D("20000.00")
    assert second.get(TAXABLE_CAPITAL_GAINS).value == D("100000.00")
    assert second.get(QBT_TAXABLE_GAINS_LIMIT).value == D("20000.00")
    assert second.get(QBT_TAXABLE_GAINS_NOT_LIMITED).value == D("0")


def test_note_2_takes_the_earlier_line_41_from_line_23() -> None:
    # Note (2): line 23 of the next form is 4,000.00 - 4,000.00 (the first form's line 41) = 0.00.
    first, second = qbts("40000", "0")

    assert second.get(QBT_EARLIER_ABIL_REDUCTION_TOTAL).value == first.get(QBT_ABIL_REDUCTION).value
    assert second.get(QBT_EARLIER_ABIL_REDUCTION_TOTAL).value == D("4000.00")
    assert second.get(ALLOWABLE_BUSINESS_INVESTMENT_LOSS).value == D("4000.00")
    assert second.get(QBT_ALLOWABLE_BUSINESS_INVESTMENT_LOSS_AFTER_EARLIER).value == D("0.00")


def test_note_3_takes_the_earlier_line_42_from_chart_a_line_20() -> None:
    # Note (3): the next form's Chart A line 20 is 35,000.00 (line 10, with line 18 at 0 and
    # nothing else on line 19) - 15,000.00 (the first form's line 42) = 20,000.00, line 24.
    first, second = qbts("40000", "0")

    assert second.get(QBT_EARLIER_NET_INVESTMENT_LOSS_REDUCTION_TOTAL).value == (
        first.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value
    )
    assert second.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("35000.00")
    assert second.get(QBT_CHART_A_NET_INVESTMENT_LOSS_AFTER_EARLIER).value == D("20000.00")


def test_the_second_run_works_from_the_corrected_lines() -> None:
    # Line 25 is 0 + 0.00 + 20,000.00 = 20,000.00 and line 26 is 20,000.00 - 20,000.00 = 0, so
    # nothing can be claimed (0). Line 28 is 20,000.00, line 30 is 20,000.00 and line 32 is
    # 20,000.00; line 35 is 0.00 + 20,000.00; line 36 is 20,000.00; line 41 is 0.00 x 20,000.00 /
    # 20,000.00 = 0.00 and line 42 is 20,000.00.
    _, second = qbts("40000", "0")

    assert second.get(QBT_MAXIMUM_DEDUCTION).value == D("0")
    assert second.get(QBT_CAPITAL_GAINS_DEDUCTION).value == D("0")
    assert second.get(QBT_ALLOCATION_TOTAL).value == D("20000.00")
    assert second.get(QBT_ABIL_REDUCTION).value == D("0.00")
    assert second.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D("20000.00")


def test_a_third_run_subtracts_the_sum_of_both_earlier_runs() -> None:
    # Line 32: 80,000.00 + 20,000.00 = 100,000.00, so line 8 is 0.00; line 41: 4,000.00 + 0.00, so
    # line 23 is 0.00; line 42: 15,000.00 + 20,000.00 = 35,000.00, so Chart A line 20 is 0.00.
    *_, third = qbts("40000", "0", "0")

    assert third.get(QBT_EARLIER_ALLOCATION_TOTAL).value == D("100000.00")
    assert third.get(QBT_EARLIER_ABIL_REDUCTION_TOTAL).value == D("4000.00")
    assert third.get(QBT_EARLIER_NET_INVESTMENT_LOSS_REDUCTION_TOTAL).value == D("35000.00")
    assert third.get(QBT_TAXABLE_CAPITAL_GAINS_AFTER_EARLIER).value == D("0.00")
    assert third.get(QBT_ALLOWABLE_BUSINESS_INVESTMENT_LOSS_AFTER_EARLIER).value == D("0.00")
    assert third.get(QBT_CHART_A_NET_INVESTMENT_LOSS_AFTER_EARLIER).value == D("0.00")


def test_the_return_totals_each_line_over_the_dispositions() -> None:
    # Line 32: 80,000.00 + 20,000.00; line 41: 4,000.00 + 0.00; line 42: 15,000.00 + 20,000.00;
    # line 25395: 40,000 + 0; Part 5 B (17212) is line 7 of each, 150,000.00 + 150,000.00.
    runs = scenario(tuple({**QBT, "qbt_deduction_claimed": c} for c in ("40000", "0")))
    worksheet = runs["ca-on/return"][0]

    assert worksheet.get(QBT_ALLOCATION_TOTAL).value == D("100000.00")
    assert worksheet.get(QBT_ABIL_REDUCTION).value == D("4000.00")
    assert worksheet.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D("35000.00")
    assert worksheet.get(QBT_CAPITAL_GAINS_DEDUCTION).value == D("40000")
    assert worksheet.get(QBT_ELECTION_DEDUCTION).value == D("300000.00")


# --- "You must claim any deduction under a QBT before any deduction under a QCC." ----------------


def listed(*kinds: str) -> list[Worksheet]:
    """The runs for dispositions that are QBTs ("qbt") or QCCs ("qcc"), in this order."""
    rows = tuple({"qbt_election_is_qbt": 1 if kind == "qbt" else 0} for kind in kinds)
    return list(run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=rows)["ca/t2048"])


@pytest.mark.parametrize(
    "order",
    [
        ("qbt",),
        ("qcc",),
        ("qbt", "qbt"),
        ("qbt", "qcc"),
        ("qcc", "qcc"),
        ("qbt", "qbt", "qcc", "qcc"),
    ],
)
def test_a_qbt_before_any_qcc_is_in_order(order: tuple[str, ...]) -> None:
    runs = listed(*order)

    assert [w.get(QBT_ELECTION_IS_QBT_IN_ORDER).value for w in runs] == [
        1 if kind == "qbt" else 0 for kind in order
    ]


def test_a_qcc_listed_before_a_qbt_is_an_input_error_at_the_qbt() -> None:
    with pytest.raises(ValidationError) as raised:
        listed("qcc", "qbt")

    assert str(raised.value) == (
        "ca/t2048, instance 2: ca/qbt_election_is_qbt is 1 but disposition 1 before it is a QCC: "
        "the QBT must come before the QCC"
    )


def test_the_error_names_the_later_qbt_s_position_and_the_first_qcc_before_it() -> None:
    with pytest.raises(ValidationError) as raised:
        listed("qbt", "qcc", "qcc", "qbt")

    assert str(raised.value).startswith("ca/t2048, instance 4: ")
    assert "disposition 2 before it is a QCC" in str(raised.value)
    assert "the QBT must come before the QCC" in str(raised.value)


def test_a_qbt_listed_after_a_qcc_is_refused_even_with_no_figures() -> None:
    # The order is the filer's designation; the check reads the answers only, not the amounts.
    with pytest.raises(ValidationError, match="QBT must come before the QCC"):
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            t2048_dispositions_rows=({"qbt_election_is_qbt": 0}, {"qbt_election_is_qbt": 1}),
        )


def test_chart_a_line_20_after_note_3_is_floored_at_0_for_a_second_disposition() -> None:
    # Taxable capital gains (line 12700) of 100,000.00 and carrying charges of 10,000.
    # Disposition 1: line 7 is 20,000.00, line 8 is 100,000.00, line 17 is 100,000.00 and Chart
    # A line 20 is 10,000.00 (line 10 less a line 19 of 0), with investment expenses, so line 24
    # is 10,000.00; line 26 is 90,000.00 and nothing is claimed (0). Line 30 is 20,000.00 and
    # line 32 is 20,000.00; line 35 is 10,000.00, line 36 is 10,000.00, line 41 is 0.00 and
    # line 42 is 10,000.00. Disposition 2: line 8 is 100,000.00 -
    # 20,000.00 = 80,000.00 and line 16 is 0, so line 17 is 0 and Chart A line 18 is 80,000.00;
    # Chart A line 20 is 10,000.00 - 80,000.00, entered as 0 ("if negative enter 0"). Note (3) is
    # printed on line 20, whose floor applies to the result: 0 - 10,000.00 is entered as 0.00;
    # line 24 is 0. The one investment expenses answer of the year is 1 for both dispositions.
    first = {
        "qbt_election_eligible_amount": "40000",
        "qbt_percentage_allocated": "100",
        "qbt_capital_gains": "200000",
        "qbt_election_is_qbt": 1,
        "qbt_deduction_claimed": "0",
    }
    second = {
        "qbt_election_eligible_amount": "1000000",
        "qbt_percentage_allocated": "100",
        "qbt_capital_gains": "0",
        "qbt_election_is_qbt": 1,
        "qbt_deduction_claimed": "0",
    }
    runs = run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        slip_capital_gains_or_losses="200000",
        total_carrying_charges="10000",
        has_investment_expenses=1,
        t2048_dispositions_rows=(first, second),
    )
    one, two = runs["ca/t2048"]

    assert one.get(QBT_NET_INVESTMENT_LOSS).value == D("10000.00")
    assert one.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D("10000.00")
    assert two.get(QBT_EARLIER_NET_INVESTMENT_LOSS_REDUCTION_TOTAL).value == D("10000.00")
    assert two.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("0")
    assert two.get(QBT_CHART_A_NET_INVESTMENT_LOSS_AFTER_EARLIER).value == D("0.00")
    assert two.get(QBT_NET_INVESTMENT_LOSS).value == D("0")
    assert two.get(QBT_MAXIMUM_DEDUCTION).value == D("0")
    assert two.get(QBT_ALLOCATION_TOTAL).value == D("0")
    assert two.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D("0")
    # Part 5: line 32 20,000.00 + 0.00; line 42 10,000.00 + 0.00; B (17212) is line 7 of each,
    # 20,000.00 + 500,000.00; C (17213) is line 16, 100,000.00 + 0.00; D (17215) is lines 31 and
    # 36, (0 + 10,000.00) + (0 + 0.00).
    worksheet = runs["ca-on/return"][0]
    assert worksheet.get(QBT_ALLOCATION_TOTAL).value == D("20000.00")
    assert worksheet.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D("10000.00")
    assert worksheet.get(QBT_ELECTION_DEDUCTION).value == D("520000.00")
    assert worksheet.get(QBT_TAXABLE_CAPITAL_GAINS).value == D("100000.00")
    assert worksheet.get(QBT_TAXABLE_GAINS_RELATED_TO_DEDUCTION).value == D("10000.00")
    assert worksheet.get(QBT_CAPITAL_GAINS_DEDUCTION).value == D("0")


@pytest.mark.parametrize(
    ("business_investment_loss", "abil", "line_41", "line_42", "line_27"),
    [("0", "0.00", "0.00", "0.00", "0.00"), ("40000", "6666.67", "0.00", "0.00", "-6666.67")],
)
def test_a_second_disposition_with_investment_expenses_floors_chart_a_line_20_at_0(
    business_investment_loss: str, abil: str, line_41: str, line_42: str, line_27: str
) -> None:
    # Taxable capital gains of 100,000.00, carrying charges of 10,000 and, in the second case, a
    # business investment loss of 40,000 (ABIL 20,000.00). Disposition 1 as above (line 24 is
    # 10,000.00, line 32 is 20,000.00); with the ABIL its line 35 is 30,000.00, line 36 is
    # 20,000.00, line 41 is 20,000.00 x 20,000.00 / 30,000.00 = 13,333.33 and line 42 is 6,666.67
    # (0.00 and 10,000.00 without it). Disposition 2, with investment expenses: line 8 is
    # 80,000.00, line 17 is 0, Chart A line 20 is 10,000.00 - 80,000.00, entered as 0, and note
    # (3) takes the earlier line 42 from it: still 0, so line 24 is 0. Line 23 is the ABIL less
    # the earlier line 41: 20,000.00 - 13,333.33 = 6,666.67 in the second case. Line 26 is 0 less
    # line 25 (0 without the ABIL, 6,666.67 with it), so line 26 and line 27 are 0.00 or -6,666.67,
    # as the form prints them, and nothing can be claimed; line 28 is 0, so lines 30, 32, 36, 41
    # and 42 are 0.
    first = {
        "qbt_election_eligible_amount": "40000",
        "qbt_percentage_allocated": "100",
        "qbt_capital_gains": "200000",
        "qbt_election_is_qbt": 1,
        "qbt_deduction_claimed": "0",
    }
    second = {**first, "qbt_election_eligible_amount": "1000000", "qbt_capital_gains": "0"}
    runs = run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        slip_capital_gains_or_losses="200000",
        total_carrying_charges="10000",
        business_investment_loss=business_investment_loss,
        has_investment_expenses=1,
        t2048_dispositions_rows=(first, second),
    )
    _, two = runs["ca/t2048"]

    assert two.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("0")
    assert two.get(QBT_CHART_A_NET_INVESTMENT_LOSS_AFTER_EARLIER).value == D("0")
    assert two.get(QBT_NET_INVESTMENT_LOSS).value == D("0")
    assert two.get(QBT_ALLOWABLE_BUSINESS_INVESTMENT_LOSS_AFTER_EARLIER).value == D(abil)
    assert two.get(QBT_MAXIMUM_DEDUCTION).value == D(line_27)
    assert two.get(QBT_ALLOCATION_TOTAL).value == D("0")
    assert two.get(QBT_ABIL_REDUCTION).value == D(line_41)
    assert two.get(QBT_NET_INVESTMENT_LOSS_REDUCTION).value == D(line_42)


@pytest.mark.parametrize(("answer", "line_24"), [(1, "10000.00"), (0, "0")])
def test_the_one_investment_expenses_answer_of_the_year_gates_line_24_of_every_disposition(
    answer: int, line_24: str
) -> None:
    # Taxable capital gains of 100,000.00 and carrying charges of 10,000, so Chart A line 20 is
    # 10,000.00 on the first disposition. Part 3 line 24 is that figure when the year's one answer
    # to "If you have investment expenses in 2025" is 1 and "0" otherwise, the same for the second
    # disposition (whose note (3) floor puts its own Chart A line 20 at 0 either way).
    first = {
        "qbt_election_eligible_amount": "40000",
        "qbt_percentage_allocated": "100",
        "qbt_capital_gains": "200000",
        "qbt_election_is_qbt": 1,
        "qbt_deduction_claimed": "0",
    }
    second = {**first, "qbt_election_eligible_amount": "1000000", "qbt_capital_gains": "0"}
    runs = run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        slip_capital_gains_or_losses="200000",
        total_carrying_charges="10000",
        has_investment_expenses=answer,
        t2048_dispositions_rows=(first, second),
    )
    one, two = runs["ca/t2048"]

    assert one.get(QBT_HAS_INVESTMENT_EXPENSES).value == answer
    assert two.get(QBT_HAS_INVESTMENT_EXPENSES).value == answer
    assert one.get(QBT_NET_INVESTMENT_LOSS).value == D(line_24)
    assert two.get(QBT_NET_INVESTMENT_LOSS).value == D("0")


def test_an_investment_expenses_answer_above_one_is_refused() -> None:
    with pytest.raises(InputAboveBoundError):
        run(
            "0",
            (),
            "0",
            "0",
            "0",
            "0",
            "0",
            has_investment_expenses=2,
            t2048_dispositions_rows=({"qbt_election_is_qbt": 1},),
        )


def partnership_scenario(partnership_taxable_capital_gains: str = "0") -> list[Worksheet]:
    # A line 12200 amount of 20,000 and no taxable capital gains elsewhere, so Chart A line 19 is
    # the partnership part alone; other investment expenses of 30,000 make line 10 30,000.
    row = {**QBT, "qbt_deduction_claimed": "0"}
    runs = run(
        "0",
        (),
        "0",
        "0",
        "0",
        "0",
        "0",
        net_partnership_income="20000",
        other_investment_expenses="30000",
        partnership_taxable_capital_gains=partnership_taxable_capital_gains,
        t2048_dispositions_rows=(row,),
    )
    return list(runs["ca/t2048"])


def test_chart_a_line_13_is_line_12200_other_than_the_taxable_capital_gains() -> None:
    # Line 12200 is 20,000.00 and includes taxable capital gains of 5,000.00: line 13 is
    # 15,000.00, so line 19 is 15,000.00 and line 20 is 30,000.00 - 15,000.00 = 15,000.00.
    (only,) = partnership_scenario(partnership_taxable_capital_gains="5000")

    assert only.get(QBT_PARTNERSHIP_INCOME_OTHER_THAN_GAINS).value == D("15000.00")
    assert only.get(QBT_INVESTMENT_INCOME).value == D("15000.00")
    assert only.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("15000.00")


def test_chart_a_line_13_is_all_of_line_12200_with_no_taxable_capital_gains_in_it() -> None:
    # Without the carve-out line 13 is the whole 20,000.00 and line 20 is 10,000.00.
    (only,) = partnership_scenario()

    assert only.get(QBT_PARTNERSHIP_INCOME_OTHER_THAN_GAINS).value == D("20000.00")
    assert only.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("10000.00")


def test_the_taxable_capital_gains_equal_to_line_12200_leave_line_13_at_0() -> None:
    (only,) = partnership_scenario(partnership_taxable_capital_gains="20000")

    assert only.get(QBT_PARTNERSHIP_INCOME_OTHER_THAN_GAINS).value == D("0.00")
    assert only.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("30000.00")


def test_taxable_capital_gains_above_line_12200_leave_line_13_negative() -> None:
    # The form prints no limit or floor: 20,000.00 less 25,000.00 is (5,000.00), line 19 is
    # (5,000.00) and line 20 is 30,000.00 - (5,000.00) = 35,000.00.
    (only,) = partnership_scenario(partnership_taxable_capital_gains="25000")

    assert only.get(QBT_PARTNERSHIP_INCOME_OTHER_THAN_GAINS).value == D("-5000.00")
    assert only.get(QBT_INVESTMENT_INCOME).value == D("-5000.00")
    assert only.get(QBT_CHART_A_NET_INVESTMENT_LOSS).value == D("35000.00")


def test_a_line_6_above_line_5_is_an_input_error_not_a_floor() -> None:
    # Line 5 is 100,000 x 100% x 50% = 50,000.00; a line 6 of 60,000 is refused at line 6.
    rows = {**DOLLARS, "qbt_prior_years_claims": "60000"}
    with pytest.raises(InputAboveBoundError) as raised:
        run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=(rows,))

    assert str(raised.value) == (
        "ca/t2048, instance 1: ca/qbt_prior_years_claims 60000 is above "
        "ca/qbt_taxable_amount_allocated 50000.00"
    )


def test_a_line_13_above_line_12_is_an_input_error_not_a_floor() -> None:
    # Line 12 is 5,000 (line 9) + 0 (line 10); a line 13 of 8,000 is refused at line 13.
    rows = {**DOLLARS, "qbt_capital_gains": "5000", "qbt_2025_reserve": "8000"}
    with pytest.raises(InputAboveBoundError) as raised:
        run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=(rows,))

    assert str(raised.value) == (
        "ca/t2048, instance 1: ca/qbt_2025_reserve 8000 is above "
        "ca/qbt_capital_gains_with_2024_reserve 5000"
    )


def test_lines_6_and_13_equal_to_lines_5_and_12_are_accepted() -> None:
    # Line 5 is 50,000.00 and line 6 is 50,000, so line 7 is 0; line 12 is 5,000 and line 13 is
    # 5,000, so line 14 is 0.
    rows = {
        **DOLLARS,
        "qbt_prior_years_claims": "50000",
        "qbt_capital_gains": "5000",
        "qbt_2025_reserve": "5000",
    }
    (one,) = run("0", (), "0", "0", "0", "0", "0", t2048_dispositions_rows=(rows,))["ca/t2048"]

    assert one.get(QBT_DEDUCTION_AVAILABLE).value == D("0.00")
    assert one.get(QBT_TOTAL_CAPITAL_GAINS).value == D("0.00")
