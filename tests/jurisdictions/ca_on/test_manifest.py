"""The CA-ON manifest: what it selects, and that it builds into a set of forms (a `FormSet`).

Building it through `TaxComputationService.compose` resolves every slot: each capability name to a
registered class, each parameter slot's family to a dataset of the slot's kind for the tax year,
and each artifact identifier to a registered kind of the slot's value type.

The entries it selects are listed by family, one module each in `manifest_families/`: each
family test checks that its own entries are in the manifest, and the full-manifest tests check
that the families together are the whole manifest, so an entry outside every family still
fails.
"""

from __future__ import annotations

from types import ModuleType

import pytest

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Manifest
from tests.jurisdictions.ca_on.end_to_end.support import service
from tests.jurisdictions.ca_on.manifest_families import (
    alternative_minimum_tax,
    canada_workers_benefit,
    capital_gains_deduction_t657,
    capital_gains_deduction_t657_charts,
    capital_gains_deduction_t657_charts_2016_to_2020,
    capital_gains_deduction_t657_charts_2021_to_2023,
    cpp_lines,
    cpp_t4_slip_checks,
    credits_against_federal_tax,
    deductions,
    deductions_schedule_8_part_5,
    deductions_schedule_8_part_5_contributions,
    deductions_schedule_8_part_5_other_earnings,
    has_investment_expenses,
    immediate_expensing_total,
    income,
    investment_tax_credit,
    multigenerational_home_renovation_credit,
    net_tax,
    non_active_partnership_losses,
    non_refundable_credits,
    on_ben_residences,
    ontario_alternative_minimum_tax,
    ontario_benefit_inputs,
    ontario_credits,
    ontario_lift,
    ontario_other_credits,
    ontario_personal_amounts,
    ontario_tax_reduction,
    other_employment_expenses,
    other_inputs,
    other_investment_expenses,
    other_property_income,
    partnership_taxable_capital_gains,
    personal_amounts,
    rc359,
    rc381_cpp_qpp,
    refund,
    refundable_credits,
    rental_cca_limit_all_statements,
    resp_aips,
    restricted_farm_loss_applied,
    rrsp_fhsa,
    schedule_3,
    schedule_8,
    security_options_boxes_39_and_91,
    security_options_boxes_41_and_92,
    spouse_on_december_31,
    t1_m,
    t90,
    t657_chart_amounts_from_t2017,
    t746,
    t776,
    t777,
    t929,
    t936,
    t1032_pension_income_splitting,
    t1043,
    t1139,
    t1206_share_dispositions,
    t1212,
    t2017_reserve,
    t2042,
    t2043,
    t2048,
    t2121,
    t2125,
    t2205,
    taxable_income,
    us_social_security_treaty_deduction,
    yes_or_no_flag_checks,
)

FAMILIES: tuple[ModuleType, ...] = (
    income,
    immediate_expensing_total,
    t1_m,
    t776,
    rental_cca_limit_all_statements,
    t2042,
    t2043,
    t2121,
    t2125,
    t777,
    rc359,
    rrsp_fhsa,
    deductions,
    schedule_8,
    cpp_lines,
    cpp_t4_slip_checks,
    taxable_income,
    t2048,
    t929,
    schedule_3,
    spouse_on_december_31,
    t1032_pension_income_splitting,
    t1043,
    t1206_share_dispositions,
    t746,
    t1139,
    t90,
    t936,
    t2205,
    t1212,
    t2017_reserve,
    t657_chart_amounts_from_t2017,
    security_options_boxes_39_and_91,
    security_options_boxes_41_and_92,
    has_investment_expenses,
    non_active_partnership_losses,
    other_investment_expenses,
    other_property_income,
    partnership_taxable_capital_gains,
    capital_gains_deduction_t657,
    capital_gains_deduction_t657_charts,
    capital_gains_deduction_t657_charts_2016_to_2020,
    capital_gains_deduction_t657_charts_2021_to_2023,
    personal_amounts,
    non_refundable_credits,
    rc381_cpp_qpp,
    credits_against_federal_tax,
    investment_tax_credit,
    resp_aips,
    restricted_farm_loss_applied,
    other_employment_expenses,
    other_inputs,
    net_tax,
    alternative_minimum_tax,
    canada_workers_benefit,
    refundable_credits,
    refund,
    multigenerational_home_renovation_credit,
    ontario_personal_amounts,
    ontario_credits,
    ontario_tax_reduction,
    ontario_alternative_minimum_tax,
    ontario_lift,
    ontario_other_credits,
    ontario_benefit_inputs,
    on_ben_residences,
    us_social_security_treaty_deduction,
    yes_or_no_flag_checks,
)

ROOTS = tax_engine.registrations.JURISDICTIONS.roots()
CA_ON = JurisdictionCode("CA-ON")
# The three Part 5 modules hold only steps of the form `ca/schedule_8`, which
# `test_manifest_schedule_8.py` checks, and the manifest inputs those steps read.
SCHEDULE_8_PART_5_FAMILIES: tuple[ModuleType, ...] = (
    deductions_schedule_8_part_5,
    deductions_schedule_8_part_5_contributions,
    deductions_schedule_8_part_5_other_earnings,
)
INPUTS = frozenset[str]().union(
    *(family.INPUTS for family in (*FAMILIES, *SCHEDULE_8_PART_5_FAMILIES))
)
OUTPUTS = frozenset[str]().union(*(family.OUTPUTS for family in FAMILIES))
STEPS = set[CapabilitySelection]().union(*(family.STEPS for family in FAMILIES))
WIRING = set[object]().union(*(family.WIRING for family in FAMILIES))


def manifest() -> Manifest:
    (only,) = YamlJurisdictionSource(ROOTS).get_jurisdiction(CA_ON).manifests
    return only


@pytest.mark.parametrize("family", FAMILIES, ids=[f.__name__.rpartition(".")[2] for f in FAMILIES])
def test_the_manifest_has_the_inputs_outputs_and_selections_of_the_family(
    family: ModuleType,
) -> None:
    found = manifest()

    assert family.INPUTS <= found.inputs.keys()
    assert family.OUTPUTS <= set(found.forms[0].exports)
    assert family.STEPS <= set(found.forms[0].capabilities)


@pytest.mark.parametrize("family", FAMILIES, ids=[f.__name__.rpartition(".")[2] for f in FAMILIES])
def test_the_composition_has_the_wiring_of_the_family(family: ModuleType) -> None:
    composition = service().compose(CA_ON, 2025).form("ca-on/return").composition

    wiring = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composition.order
    }
    assert family.WIRING <= wiring


def test_ca_on_has_one_manifest_from_2025() -> None:
    found = manifest()

    assert found.jurisdiction == CA_ON
    assert found.version == 1
    assert found.valid_from_tax_year == 2025
    assert found.inputs.keys() == INPUTS
    # T1 line 167, the refund or balance owing, Schedule 7 line 23, what the return produces for
    # the next year's line 1, line 12010, the amount of dividends other than eligible, which
    # nothing else on the return reads; the Federal Worksheet's "Line 25000 - Other payments
    # deduction" line 9 "Line 5 plus line 8 =", which nothing consumes while the count of line 9
    # over $93,454 is a starting count; and ON428 line 58, the Ontario tax less the dividend tax
    # credit, which only line 60 (the lesser of line 58 and the minimum tax carryover credit) reads,
    # so it is also a line the computation returns; Schedule 15 line 58, what the return produces
    # for the next year's line 52; the Ontario opportunities fund's line 3 (line 46600) "Net
    # refund (line 1 minus line 2)", which nothing reads (line 48400, the refund, is read by that
    # page's line 1, so it is not a line the computation returns); and ON479 line 63260, the
    # number of eligible work placements, which nothing else reads; Schedule 8 Part 2 line C
    # "Maximum amount subject to second additional contributions" of the "Monthly proration for
    # 2025" table, which nothing consumes, as Part 4 line 12 reads the maximum of 9,900 (and the
    # 8% rate) from its own dataset; T776 line 8140 "Total of
    # your gross rents for short-term rentals", which nothing else reads; T776 line 9365 "Total
    # for short-term rental portion", which nothing else reads (Chart A's column 3 is a
    # starting amount); Schedule 11 line 25 "Unused federal tuition amount available to carry
    # forward to a future year", which nothing else reads; T776 Area A column 24 "UCC at the end
    # of the year", a record list of each class's closing UCC for next year, which nothing else
    # reads; Form T2222 Chart A's row C
    # "Enter the total of all amounts in row B. This total cannot be more than $1,200.", totalled
    # over the individuals, which no line of the form reads; and Form ON-BEN's nine lines (tick
    # boxes 61020, 61040, 61060, 61070 and 61140, Part A lines 61100, 61120, 61210 and 61230),
    # which the return carries as entered, each also an input with nothing computing from it;
    # Form ON-BEN line 61080 "separate principal residences for medical reasons", checked against
    # the spouse fact and carried as the spouse-answer kind (part `28_on_ben_checks.yaml`); and
    # ON479 line 63265 (the
    # answer on a partnership claim) and line 63270 (the business number), likewise carried as
    # entered: the lines the computation returns.
    # T1 line 21999 "Total" is read by the line 22000 check (`core/at_most`), so it is no memo.
    # T1 lines 10105 to 12799, 20600 and 26600 (the printed memo lines), Schedule 11 lines
    # 32005, 32010 and 32020 and Schedule 15 lines 68930, 59 and 68960 and 68965, each carried as
    # entered: also an input with nothing computing from it (lines 10120, 11410 and 11905 are
    # already included in lines 10100, 11400 and 11900, so they are not added to total income).
    # Schedule ON(S11) line 8, "Unused provincial tuition and education amounts available to carry
    # forward to a future year", the carryforward, which nothing else on the return reads.
    # Form T2048 Part 4 line 32 "Line 30 plus line 31", which nothing reads, and Part 5's totals A
    # 17211, B 17212, D 17215, E 17216 and (as lines 16, 41 and 42) C 17213, F 17217 and G 17218,
    # which the return carries for Form T657 and the T1 slips. Form T657 Chart 2025 Part 1 amount
    # Q, "If you are not disposing of any other QFFP or QSBCS in 2025, this is the maximum amount
    # you can claim on line 25400", which nothing reads (Part 2's amount Q caps line 25400).
    # Form T657 Chart 2024 Period 1 and Period 2 amount O, "Enter whichever is less: line 21 of
    # Step 1, line 19 of Step 2 or amount N above", which nothing reads (Chart 2025 reads Period 2's
    # amount N).
    # Form T657 Charts 2021, 2022 and 2023 Part 1 amount N and Part 2 amount M, "Enter whichever is
    # less: line 21 of Step 1, line 19 of Step 2 or amount M above" and "... or amount L above",
    # the maximum for line 25400 when no later reserve is reported, which nothing reads (the total
    # carried forward is what the next chart reads).
    # Form T657 Charts 2016 to 2020 Part 1 amount H and Part 2 amount K, the maximum for line 25400
    # when
    # no later reserve is reported, which nothing reads (the carried total is what the next chart
    # reads).
    # Form T2038(IND) Part A "Total current-year refundable credits (add amounts 1 to 4)", amount A,
    # and Part B "Total current-year non-refundable tax credits (add amounts B, C, D and E)", amount
    # F, are read by Part D ("Current-year refundable tax credit (amount A in Part A)" at amount 2
    # and "Current-year non-refundable tax credit (amount F in Part B)" at amount 3), so they are no
    # longer declared outputs.
    assert set(found.forms[0].exports) == OUTPUTS
    # List order carries no meaning: the composition derives the run order from the contracts.
    assert set(found.forms[0].capabilities) == STEPS
    assert len(found.forms[0].capabilities) == len(set(found.forms[0].capabilities))
    # T2125 Area A column 22 "UCC at the end of the year", a record list of each class's closing UCC
    # for next year, and Part 7 line 7O "Business-use-of-home expenses available to carry forward",
    # which nothing else on the return reads.
    assert set(found.forms[0].exports) == OUTPUTS
    # List order carries no meaning: the composition derives the run order from the contracts.
    assert set(found.forms[0].capabilities) == STEPS
    assert len(found.forms[0].capabilities) == len(set(found.forms[0].capabilities))
    # Form T691 Part 1 line 12 "Add lines 1, 4, 7, and 11.", the adjusted taxable income subtotal,
    # Part 9 line 6 "Enter this amount on line 14 of Part 1", Part 1 line 20 "Line 15 minus line 19"
    # and Part 1 line 26 "Line 24 minus line 25" times 30%, which nothing else on the return reads
    # yet.
    assert set(found.forms[0].exports) == OUTPUTS
    # List order carries no meaning: the composition derives the run order from the contracts.
    assert set(found.forms[0].capabilities) == STEPS
    assert len(found.forms[0].capabilities) == len(set(found.forms[0].capabilities))
    # Form T691 Part 1 line 27 "Add lines 13, 14, 23, and 26.", which nothing else on the return
    # reads yet (lines 12, 14, 20 and 26 are read by lines 13, 14, 22, 23 and 27, so they are no
    # longer declared outputs).
    # Form T691 Part 5 line 11 "Line 7 minus line 10 (if negative, enter "0")" is read by the count
    # of the condition "line 11 is positive" for T1 line 41700; Part 5 lines 1 to 10 are read by the
    # lines after them, and Part 3 line 15 and Part 4 line 11 are read by Part 5 lines 4 and 2, so
    # none of them is a declared output.
    # Form T691 Part 6 line 14 "Enter whichever is more: amount from line 12 or line 13. Enter this
    # amount on line 41700 of your return." is read by the choice of T1 line 41700 (the figure is
    # entered only when Part 5 line 11 is positive), so it is no longer a declared output; Part 6
    # lines 1 to 13 are read by the lines after them.
    assert set(found.forms[0].exports) == OUTPUTS
    # List order carries no meaning: the composition derives the run order from the contracts.
    assert set(found.forms[0].capabilities) == STEPS
    assert len(found.forms[0].capabilities) == len(set(found.forms[0].capabilities))


def test_its_first_tax_year_composes_every_selection() -> None:
    composition = service().compose(CA_ON, 2025).form("ca-on/return").composition

    wiring = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composition.order
    }
    assert len(composition.order) == len(wiring)
    assert wiring == WIRING
