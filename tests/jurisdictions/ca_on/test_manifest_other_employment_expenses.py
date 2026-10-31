"""T1 line 22900 "Other employment expenses (see Guide T4044)" in the CA-ON manifest.

Line 22900 is computed, no longer a starting input: `ca/other_employment_expenses` is the total of
Form T777 line 17 (`ca/t777_line_17`) and the total of Form RC359 line 7 over the copies
(`ca/rc359_excess_epsp_total`). The two steps are in `05s_other_employment_expenses.yaml`. The line
23300 sum of `05_deductions.yaml` takes the kind as one of its parts, in line order after line 22400
(`ca/exploration_and_development_expenses`) and before line 23100 (`ca/clergy_residence_deduction`).
The steps that read the kind (the medical supplement's employment deductions in
`13_refundable_credits.yaml` and T691 Part 1 line 77 in `20_alternative_minimum_tax.yaml`) are
unchanged.

The entries are listed in `manifest_families/other_employment_expenses.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Manifest
from tests.jurisdictions.ca_on.manifest_families import other_employment_expenses
from tests.jurisdictions.ca_on.manifest_support import inputs_text

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
PART = MANIFESTS / "05s_other_employment_expenses.yaml"
DEDUCTIONS_PART = MANIFESTS / "05_deductions.yaml"
INPUTS_PART = MANIFESTS / "01_inputs.yaml"
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
LINE_22900 = "ca/other_employment_expenses"
RC359_TOTAL = "ca/rc359_excess_epsp_total"
T777_LINE_17_DERIVED = "ca/t777.t777_line_17"
T777_LINE_17_TOTAL = "ca/t777_line_17_total"


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def referenced(values: Iterable[object]) -> set[str]:
    """Every identifier named by the values of a selection's slots (a slot may hold a tuple)."""
    names: set[str] = set()
    for value in values:
        if isinstance(value, tuple):
            names |= set(value)
        else:
            names.add(str(value))
    return names


def producer_of(identifier: str) -> CapabilitySelection:
    (found,) = (
        each for each in manifest().forms[0].capabilities if identifier in each.produces.values()
    )
    return found


# --- the part and its layout ----------------------------------------------------------------------


def test_the_line_22900_part_is_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    assert LAYOUT.match(PART.name), PART.name
    assert PART.stat().st_size <= 30 * 1024


def test_the_deductions_part_stays_under_30_kb_after_the_one_line_change() -> None:
    assert DEDUCTIONS_PART.stat().st_size <= 30 * 1024


def test_the_part_is_a_part_of_the_return_and_declares_no_form() -> None:
    assert "form" not in yaml.safe_load(PART.read_text())


# --- the steps of the return ----------------------------------------------------------------------


def test_the_family_holds_the_three_steps_and_the_return_selects_them() -> None:
    assert len(other_employment_expenses.STEPS) == 3
    assert other_employment_expenses.STEPS <= set(manifest().forms[0].capabilities)


def test_the_rc359_line_7_total_is_a_record_total_over_the_copies_of_the_form() -> None:
    step = producer_of(RC359_TOTAL)

    assert step.name == "core/record_total"
    assert step.consumes == {"records": "ca/rc359.rc359_excess_epsp_amount"}


def test_line_22900_is_the_sum_of_the_t777_line_17_and_the_rc359_line_7_total() -> None:
    step = producer_of(LINE_22900)

    assert step.name == "core/sum"
    assert step.consumes == {"parts": (T777_LINE_17_TOTAL, RC359_TOTAL)}


def test_the_return_reads_the_t777_line_17_only_through_its_total() -> None:
    # The form ca/t777 exports line 17 as the derived kind `ca/t777.t777_line_17`, one record, read
    # by core/record_total into `ca/t777_line_17_total`; only that total is read by line 22900.
    readers = [
        each
        for each in manifest().forms[0].capabilities
        if T777_LINE_17_DERIVED in referenced(each.consumes.values())
    ]

    assert readers == [producer_of(T777_LINE_17_TOTAL)]
    assert readers[0].name == "core/record_total"
    assert T777_LINE_17_TOTAL in referenced(producer_of(LINE_22900).consumes.values())


def test_line_22900_is_computed_and_read_by_no_input_of_the_return() -> None:
    assert LINE_22900 not in manifest().inputs.keys()
    assert RC359_TOTAL not in manifest().inputs.keys()
    assert LINE_22900 not in inputs_text()


def test_the_return_declares_no_output_for_line_22900() -> None:
    assert LINE_22900 not in set(manifest().forms[0].exports)
    assert other_employment_expenses.OUTPUTS == frozenset()


# --- the readers of line 22900 that keep reading it -----------------------------------------------


def test_the_readers_of_line_22900_are_the_deductions_and_the_two_that_read_it_as_before() -> None:
    readers = {
        output
        for each in manifest().forms[0].capabilities
        if LINE_22900 in referenced(each.consumes.values())
        for output in each.produces.values()
    }

    # The line 23300 sum (05_deductions.yaml), the medical supplement's employment deductions
    # (13_refundable_credits.yaml), T691 Part 1 line 76 "Add lines 70 to 75." at most line 69
    # (20f_amt_input_checks.yaml), and T691 Part 1 line 77 "Line 69 minus line 76"
    # (20_alternative_minimum_tax.yaml).
    assert readers == {
        "ca/deductions_from_total_income",
        "ca/medical_supplement_employment_deductions",
        "ca/amt_non_deductible_office_expenses_checked",
        "ca/amt_office_expenses_adjustment",
    }


# --- the line 23300 sum ---------------------------------------------------------------------------


def test_the_line_23300_sum_takes_line_22900_after_line_22400_and_before_line_23100() -> None:
    text = DEDUCTIONS_PART.read_text()
    parts = [line.strip() for line in text.splitlines() if line.strip().startswith("- ca/")]
    position = parts.index("- ca/exploration_and_development_expenses")

    assert parts[position : position + 3] == [
        "- ca/exploration_and_development_expenses",
        "- ca/other_employment_expenses",
        "- ca/clergy_residence_deduction",
    ]


def test_the_not_wired_comment_for_line_22900_is_gone_from_the_deductions_part() -> None:
    assert "Not wired yet: 22900" not in DEDUCTIONS_PART.read_text()
