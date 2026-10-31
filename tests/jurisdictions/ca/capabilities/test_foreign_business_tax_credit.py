"""Unit tests for the capabilities of lines 4 to 11 of Form T2209, the federal business foreign tax
credit, and their shared base `ForeignBusinessTaxCreditRows`.

Form T2209: line 4 (43400) "Business income tax paid to a foreign country (5) for the year, plus
any unused foreign tax credits for that country for the 10 years (6) before, and the 3 years after
this year"; line 5 "Net foreign business income (7) 43900" "x Basic federal tax (8)" over "Net
income (3)"; line 6 "Federal surtax on income allocated to "Other (Outside Canada)""; line 7 "Add
lines 5 and 6."; line 8 "Add basic federal tax (8) and the amount from line 6."; line 9 "Enter the
amount from line 3, if any."; line 10 "Line 8 minus line 9"; line 11 "Enter whichever is less: the
amount from line 4, 7 or 10." "Federal business foreign tax credit". Note (7): "If your net foreign
business income is more than your net income, use your net income in the calculation." Note (8):
"Line 42900 of your return plus any federal dividend tax credit (line 40425 of your return)."

The shape is Chart B's: one unregistered base works the consumed `sheets` (the T2209 sheets of
`ForeignNonBusinessTaxCredit`, which already cap the business income at net income and pool it),
and one registered subclass for each printed line produces that line's total over the sheets as
`output`. Slots of every subclass: one parameter `rounding` (a `rounding_only` dataset: the rule
for line 5, the only line that divides), three consumed `sheets`, `net_income` and
`basic_federal_tax` (note 8's figure), one produced `output`. Line 5 is the sheet's business income
times basic federal tax divided by net income as an exact fraction, rounded once; line 6 is the
sheet's own figure; line 9 is the sheet's line 3. A net income of zero or less with at least one
sheet gives line 5 of 0 without a division, and the lines that follow work from the other figures;
no sheets give 0 and do not consult net income. Each subclass records one `ForeignBusinessLine<n>`
for each sheet, by position from 1, then an `ItemsTotalLine`.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import Capability, CapabilityRegistry
from tax_engine.domain.errors import (
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
    UnknownRegistrationError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import NO_ROUNDING, RoundingMode, RoundTo
from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY, RoundingOnly
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemsTotalLine
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_line_4 import (
    ForeignBusinessTaxCreditLine4,
)
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_line_5 import (
    ForeignBusinessTaxCreditLine5,
)
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_line_7 import (
    ForeignBusinessTaxCreditLine7,
)
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_line_8 import (
    ForeignBusinessTaxCreditLine8,
)
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_line_10 import (
    ForeignBusinessTaxCreditLine10,
)
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_line_11 import (
    ForeignBusinessTaxCreditLine11,
)
from tax_engine.jurisdictions.ca.capabilities.foreign_business_tax_credit_rows import (
    ForeignBusinessTaxCreditRows,
)
from tax_engine.jurisdictions.ca.trace import (
    ForeignBusinessLine4,
    ForeignBusinessLine5,
    ForeignBusinessLine7,
    ForeignBusinessLine8,
    ForeignBusinessLine10,
    ForeignBusinessLine11,
)
from tests.jurisdictions.ca.capabilities.foreign_business_tax_credit import (
    BASIC_TAX,
    CENT,
    EXPECTED,
    NET_INCOME,
    SHEET_A,
    SHEET_B,
    SHEET_BY_NAME,
    SHEET_C,
    SHEET_E,
    SHEET_Z,
    SHEETS,
    D,
    Sheet,
    rounding,
    sheets_given,
)
from tests.manifest_support import required_inputs

# (line, capability class, registered local id, trace line class)
LINES: list[tuple[int, type[ForeignBusinessTaxCreditRows], str, type]] = [
    (4, ForeignBusinessTaxCreditLine4, "foreign_business_tax_credit_line_4", ForeignBusinessLine4),
    (5, ForeignBusinessTaxCreditLine5, "foreign_business_tax_credit_line_5", ForeignBusinessLine5),
    (7, ForeignBusinessTaxCreditLine7, "foreign_business_tax_credit_line_7", ForeignBusinessLine7),
    (8, ForeignBusinessTaxCreditLine8, "foreign_business_tax_credit_line_8", ForeignBusinessLine8),
    (
        10,
        ForeignBusinessTaxCreditLine10,
        "foreign_business_tax_credit_line_10",
        ForeignBusinessLine10,
    ),
    (
        11,
        ForeignBusinessTaxCreditLine11,
        "foreign_business_tax_credit_line_11",
        ForeignBusinessLine11,
    ),
]
LINE_NUMBERS = [line for line, *_ in LINES]
BY_LINE = {line: (cls, local_id, trace) for line, cls, local_id, trace in LINES}

# Line 10 is "Line 8 minus line 9" and is signed; the other outputs are not.
OUTPUTS: dict[int, ArtifactKind[Decimal]] = {
    line: ArtifactKind(f"ex/business_line_{line}", Decimal, non_negative=line != 10)
    for line in LINE_NUMBERS
}

by_line = pytest.mark.parametrize("line", LINE_NUMBERS, ids=[f"line_{n}" for n in LINE_NUMBERS])


def capability(
    line: int, dataset: ParameterDataset[RoundingOnly] | None = None
) -> ForeignBusinessTaxCreditRows:
    cls = BY_LINE[line][0]
    return cls(dataset or rounding(), SHEETS, NET_INCOME, BASIC_TAX, OUTPUTS[line])


def output_of(
    line: int, *rows: Sheet, dataset: ParameterDataset[RoundingOnly] | None = None, **figures: str
) -> Decimal:
    result = capability(line, dataset).compute(sheets_given(*rows, **figures))
    (output,) = result.outputs
    assert output.kind == OUTPUTS[line]
    assert isinstance(output.value, Decimal)
    return output.value


# --- contract and wiring ------------------------------------------------------------------------


@by_line
def test_is_registered_under_its_line(line: int) -> None:
    cls, local_id, _ = BY_LINE[line]

    assert CapabilityRegistry.shared().get(f"ca/{local_id}") is cls


@by_line
def test_is_exported_from_the_ca_capabilities_package(line: int) -> None:
    cls, local_id, _ = BY_LINE[line]

    assert local_id in ca_capabilities.__all__
    assert getattr(getattr(ca_capabilities, local_id), cls.__name__) is cls


@by_line
def test_is_a_subclass_of_the_shared_base(line: int) -> None:
    cls = BY_LINE[line][0]

    assert issubclass(cls, ForeignBusinessTaxCreditRows)
    assert issubclass(ForeignBusinessTaxCreditRows, Capability)


def test_the_base_is_not_registered() -> None:
    with pytest.raises(UnknownRegistrationError):
        CapabilityRegistry.shared().get("ca/foreign_business_tax_credit_rows")


@by_line
def test_declares_its_contract(line: int) -> None:
    wired = capability(line)

    assert wired.consumes == frozenset({SHEETS, NET_INCOME, BASIC_TAX})
    assert wired.produces == frozenset({OUTPUTS[line]})


@by_line
def test_leaves_its_contract_to_the_base(line: int) -> None:
    cls = BY_LINE[line][0]

    assert "consumes" not in vars(cls)
    assert "produces" not in vars(cls)


@by_line
def test_declares_its_slots(line: int) -> None:
    cls = BY_LINE[line][0]

    assert cls.PARAMETERS == {"rounding": ROUNDING_ONLY}
    assert cls.CONSUMES == {
        "sheets": RecordList,
        "net_income": Decimal,
        "basic_federal_tax": Decimal,
    }
    assert cls.PRODUCES == {"output": Decimal}
    assert not cls.is_list_slot("sheets")


@by_line
def test_its_slots_are_read_only(line: int) -> None:
    cls = BY_LINE[line][0]

    for each in (cls.PARAMETERS, cls.CONSUMES, cls.PRODUCES):
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


@by_line
def test_is_built_from_its_slot_names_as_keywords(line: int) -> None:
    cls = BY_LINE[line][0]

    wired = cls(
        rounding=rounding(),
        sheets=SHEETS,
        net_income=NET_INCOME,
        basic_federal_tax=BASIC_TAX,
        output=OUTPUTS[line],
    )

    (output,) = wired.compute(sheets_given(SHEET_A)).outputs
    assert output == Artifact(OUTPUTS[line], EXPECTED["A"][line])


@by_line
def test_takes_no_separate_rounding_argument(line: int) -> None:
    cls = cast(Any, BY_LINE[line][0])

    with pytest.raises(TypeError):
        cls(rounding(), SHEETS, NET_INCOME, BASIC_TAX, OUTPUTS[line], CENT)


@by_line
def test_rejects_a_money_kind_for_its_sheets(line: int) -> None:
    cls = cast(Any, BY_LINE[line][0])

    with pytest.raises(InvalidCapabilityError, match=f"{cls.__name__}.*'sheets'"):
        cls(rounding(), OUTPUTS[line], NET_INCOME, BASIC_TAX, OUTPUTS[line])


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        ForeignBusinessTaxCreditLine5(
            rate,  # type: ignore[arg-type]
            SHEETS,
            NET_INCOME,
            BASIC_TAX,
            OUTPUTS[5],
        )

    assert callable(wire)


# --- computing: the lines of one sheet ----------------------------------------------------------


@by_line
def test_the_worked_sheet_a(line: int) -> None:
    # One country: tax 400, unused 50, business income 6,000, net income 100,000, basic federal
    # tax (8) 14,500, line 6 = 0, line 3 = 1,400: line 4 = 450, line 5 = 870.00, line 7 = 870.00,
    # line 8 = 14,500, line 10 = 13,100, line 11 = 450.
    assert output_of(line, SHEET_A) == EXPECTED["A"][line]


@by_line
def test_a_sheet_with_a_line_6_surtax(line: int) -> None:
    # Sheet B: line 5 = 2,900.00, line 6 = 100, so line 7 = 3,000.00 and line 8 = 14,600; line 9 =
    # 100, so line 10 = 14,500; line 11 = least(900, 3,000.00, 14,500) = 900.
    assert output_of(line, SHEET_B) == EXPECTED["B"][line]


@by_line
def test_a_sheet_where_line_10_is_the_least(line: int) -> None:
    assert output_of(line, SHEET_C) == EXPECTED["C"][line]


@by_line
def test_a_sheet_where_line_7_is_the_least(line: int) -> None:
    assert output_of(line, SHEET_E) == EXPECTED["E"][line]


@by_line
def test_a_sheet_with_no_business_figures(line: int) -> None:
    # Line 8 is still the basic federal tax and line 10 is that less line 3 (0).
    assert output_of(line, SHEET_Z) == EXPECTED["Z"][line]


def test_line_4_adds_the_tax_for_the_year_to_the_unused_credits() -> None:
    assert output_of(4, ("400", "0", "0", "0", "0")) == D("400")
    assert output_of(4, ("0", "50", "0", "0", "0")) == D("50")
    assert output_of(4, ("400.25", "50.50", "0", "0", "0")) == D("450.75")


def test_line_5_does_not_read_the_taxes_or_line_6() -> None:
    assert output_of(5, ("9", "9", "6000", "9", "9")) == D("870.00")


def test_line_7_adds_line_6_to_the_rounded_line_5() -> None:
    # 6,000 x 14,500 / 100,000 = 870.00, plus 20.
    assert output_of(7, ("0", "0", "6000", "20", "0")) == D("890.00")


def test_line_8_is_the_basic_federal_tax_plus_line_6() -> None:
    assert output_of(8, ("0", "0", "0", "20", "0")) == D("14520")
    assert output_of(8, ("0", "0", "0", "20", "0"), basic_tax="9000") == D("9020")


def test_line_10_subtracts_the_sheets_line_3_from_line_8() -> None:
    assert output_of(10, ("0", "0", "0", "20", "1400")) == D("13120")


def test_line_10_may_be_negative() -> None:
    # Basic federal tax 100 plus line 6 0, less a line 3 of 500.
    assert output_of(10, ("0", "0", "0", "0", "500"), basic_tax="100") == D("-400")


def test_line_11_is_the_least_of_lines_4_7_and_10() -> None:
    assert output_of(11, ("5", "0", "6000", "0", "0")) == D("5")
    assert output_of(11, ("5000", "0", "6000", "0", "0")) == D("870.00")
    assert output_of(11, ("5000", "0", "6000", "0", "14400")) == D("100")


# --- computing: several sheets ------------------------------------------------------------------


@by_line
def test_the_output_is_the_total_over_the_sheets(line: int) -> None:
    # Sheets A and B: line 4 1,350; line 5 3,770.00; line 7 3,870.00; line 8 29,100; line 10
    # 13,100 + 14,500 = 27,600; line 11 450 + 900 = 1,350.
    assert output_of(line, SHEET_A, SHEET_B) == EXPECTED["A"][line] + EXPECTED["B"][line]


def test_the_totals_of_sheets_a_and_b_by_hand() -> None:
    assert [output_of(line, SHEET_A, SHEET_B) for line in LINE_NUMBERS] == [
        D("1350"),
        D("3770.00"),
        D("3870.00"),
        D("29100"),
        D("27600"),
        D("1350"),
    ]


@by_line
def test_the_total_does_not_depend_on_the_order_of_the_sheets(line: int) -> None:
    assert output_of(line, SHEET_B, SHEET_A, SHEET_C) == output_of(line, SHEET_C, SHEET_A, SHEET_B)


@by_line
def test_every_sheet_adds_its_line(line: int) -> None:
    names = ["A", "B", "C", "E", "Z"]

    assert output_of(line, *(SHEET_BY_NAME[n] for n in names)) == sum(
        (EXPECTED[n][line] for n in names), D("0")
    )


@by_line
def test_no_sheets_give_zero(line: int) -> None:
    assert output_of(line) == D("0")


@by_line
def test_no_sheets_do_not_consult_net_income(line: int) -> None:
    assert output_of(line, net_income="0") == D("0")


# --- computing: rounding ------------------------------------------------------------------------

# 100 of business income x 100 of basic federal tax / 300 of net income = 33.333...
THIRD: Sheet = ("1000", "0", "100", "0", "0")


def test_line_5_is_rounded_half_up_to_the_cent() -> None:
    assert output_of(5, THIRD, net_income="300", basic_tax="100") == D("33.33")


def test_line_5_rounds_a_tie_up_by_the_dataset_rule() -> None:
    # 1 x 1 / 200 = 0.005 exactly: half up gives 0.01, half even 0.00.
    tie: Sheet = ("0", "0", "1", "0", "0")
    half_even = RoundTo(D("0.01"), RoundingMode.HALF_EVEN)

    assert output_of(5, tie, net_income="200", basic_tax="1") == D("0.01")
    assert output_of(5, tie, net_income="200", basic_tax="1", dataset=rounding(half_even)) == D(
        "0.00"
    )


def test_line_5_is_rounded_once_not_after_dividing_first() -> None:
    # 0.015 x 1 / 3 is exactly 0.005, so half up gives 0.01; dividing first would give 0.00499...
    tie: Sheet = ("0", "0", "0.015", "0", "0")

    assert output_of(5, tie, net_income="3", basic_tax="1") == D("0.01")


def test_each_sheet_is_rounded_before_the_sheets_are_summed() -> None:
    # 33.33 x 3 = 99.99, not the rounded exact 100.00.
    assert output_of(5, THIRD, THIRD, THIRD, net_income="300", basic_tax="100") == D("99.99")


def test_a_whole_dollar_rule_rounds_each_sheets_line_5_to_the_dollar() -> None:
    dollar = RoundTo(D("1"), RoundingMode.HALF_UP)

    assert output_of(5, SHEET_A, dataset=rounding(dollar)) == D("870")
    assert output_of(5, THIRD, net_income="300", basic_tax="100", dataset=rounding(dollar)) == D(
        "33"
    )


def test_no_rounding_keeps_an_exact_finite_quotient() -> None:
    assert output_of(
        5, ("0", "0", "1", "0", "0"), net_income="8", basic_tax="1", dataset=rounding(NO_ROUNDING)
    ) == D("0.125")


def test_no_rounding_refuses_a_quotient_with_no_finite_expansion() -> None:
    with pytest.raises(decimal.Inexact):
        output_of(5, THIRD, net_income="300", basic_tax="100", dataset=rounding(NO_ROUNDING))


def test_a_rounded_line_5_carries_the_increments_scale() -> None:
    assert str(output_of(5, SHEET_A)) == "870.00"


def test_line_7_uses_the_rounded_line_5() -> None:
    # 33.33 + 1.50 of line 6.
    assert output_of(7, ("0", "0", "100", "1.50", "0"), net_income="300", basic_tax="100") == D(
        "34.83"
    )


def test_line_11_uses_the_rounded_line_7() -> None:
    assert output_of(11, THIRD, net_income="300", basic_tax="100") == D("33.33")


@pytest.mark.parametrize("line", [4, 8, 10])
def test_lines_that_do_not_divide_ignore_the_rounding_rule(line: int) -> None:
    assert output_of(line, SHEET_A, dataset=rounding(NO_ROUNDING)) == EXPECTED["A"][line]


# --- computing: a net income of zero or less -----------------------------------------------------

# With a net income of zero or less, line 5 is 0 without a division. The lines that follow work
# from the other figures: line 7 is line 6 alone, line 8 the basic federal tax plus line 6, line
# 10 line 8 less line 3, and line 11 the least of lines 4, 7 and 10. Line 4 keeps its tax and
# unused credits, and line 6 its surtax.
# A: line 4 = 450; line 5 = 0; line 7 = 0; line 8 = 14,500; line 10 = 14,500 - 1,400 = 13,100;
# line 11 = least(450, 0, 13,100) = 0.
# B: line 4 = 900; line 5 = 0; line 7 = 0 + 100 = 100; line 8 = 14,600; line 10 = 14,600 - 100 =
# 14,500; line 11 = least(900, 100, 14,500) = 100.
# C: line 4 = 20,000; line 5 = 0; line 7 = 0; line 8 = 14,500; line 10 = 14,500 - 14,000 = 500;
# line 11 = least(20,000, 0, 500) = 0.
# E: line 4 = 2,000; line 5 = 0; line 7 = 0; line 8 = 14,500; line 10 = 14,500 - 1,400 = 13,100;
# line 11 = least(2,000, 0, 13,100) = 0.
# Z: line 4 = 0; line 5 = 0; line 7 = 0; line 8 = 14,500; line 10 = 14,500; line 11 = 0.
ZERO_OR_LESS_EXPECTED: dict[str, dict[int, Decimal]] = {
    "A": {4: D("450"), 5: D("0"), 7: D("0"), 8: D("14500"), 10: D("13100"), 11: D("0")},
    "B": {4: D("900"), 5: D("0"), 7: D("100"), 8: D("14600"), 10: D("14500"), 11: D("100")},
    "C": {4: D("20000"), 5: D("0"), 7: D("0"), 8: D("14500"), 10: D("500"), 11: D("0")},
    "E": {4: D("2000"), 5: D("0"), 7: D("0"), 8: D("14500"), 10: D("13100"), 11: D("0")},
    "Z": {4: D("0"), 5: D("0"), 7: D("0"), 8: D("14500"), 10: D("14500"), 11: D("0")},
}
# The sheets as the non-business sheets leave them for a net income of zero or less: the business
# income is 0 there (capped at net income and floored at 0), so line 5 never reads a figure.
ZERO_INCOME_A: Sheet = ("400", "50", "0", "0", "1400")
ZERO_INCOME_B: Sheet = ("900", "0", "0", "100", "100")
ZERO_OR_LESS = pytest.mark.parametrize("net_income", ["0", "-1", "-13010"])


@by_line
@ZERO_OR_LESS
@pytest.mark.parametrize("name", ["A", "B", "C", "E", "Z"])
def test_a_net_income_of_zero_or_less_gives_each_sheet_its_line_without_line_5(
    line: int, net_income: str, name: str
) -> None:
    assert (
        output_of(line, SHEET_BY_NAME[name], net_income=net_income)
        == (ZERO_OR_LESS_EXPECTED[name][line])
    )


@by_line
@ZERO_OR_LESS
def test_a_net_income_of_zero_or_less_gives_the_total_over_the_sheets(
    line: int, net_income: str
) -> None:
    names = ["A", "B", "C", "E", "Z"]

    assert output_of(line, *(SHEET_BY_NAME[n] for n in names), net_income=net_income) == sum(
        (ZERO_OR_LESS_EXPECTED[n][line] for n in names), D("0")
    )


@by_line
@ZERO_OR_LESS
def test_a_net_income_of_zero_or_less_traces_zero_line_5_one_line_per_sheet(
    line: int, net_income: str
) -> None:
    trace = (
        capability(line)
        .compute(sheets_given(ZERO_INCOME_A, ZERO_INCOME_B, net_income=net_income))
        .trace
    )

    table = ZERO_OR_LESS_EXPECTED
    assert trace == (
        expected_line(line, 1, "A", ZERO_INCOME_A, net_income=net_income, table=table),
        expected_line(line, 2, "B", ZERO_INCOME_B, net_income=net_income, table=table),
        ItemsTotalLine(
            OUTPUTS[line],
            ((1, table["A"][line]), (2, table["B"][line])),
            table["A"][line] + table["B"][line],
        ),
    )


@by_line
@ZERO_OR_LESS
def test_a_computation_gives_the_total_for_a_net_income_of_zero_or_less(
    line: int, net_income: str
) -> None:
    worksheet = service(line).compute(
        JurisdictionCode("CA-ON"), 2025, *sheets_given(SHEET_A, SHEET_B, net_income=net_income)
    )["ca-on/return"][0]

    assert worksheet.get(OUTPUTS[line]).value == (
        ZERO_OR_LESS_EXPECTED["A"][line] + ZERO_OR_LESS_EXPECTED["B"][line]
    )


@by_line
def test_a_zero_net_income_is_worked_when_computing_not_when_wiring(line: int) -> None:
    wired = capability(line)

    assert (
        wired.compute(sheets_given(SHEET_A, net_income="0")).outputs[0].value
        == (ZERO_OR_LESS_EXPECTED["A"][line])
    )
    assert wired.compute(sheets_given(SHEET_A)).outputs[0].value == EXPECTED["A"][line]


# --- computing: inputs --------------------------------------------------------------------------


@by_line
def test_ignores_artifacts_it_does_not_consume(line: int) -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("9"))

    result = capability(line).compute((other, *sheets_given(SHEET_A)))

    assert result.outputs == (Artifact(OUTPUTS[line], EXPECTED["A"][line]),)


@by_line
@pytest.mark.parametrize("missing", ["sheets", "net_income", "basic_federal_tax"])
def test_a_missing_input_is_a_missing_artifact(line: int, missing: str) -> None:
    labels = {"sheets": "foreign_tax_credit_sheets", "net_income": "net_income"}
    inputs = list(sheets_given(SHEET_A))
    index = ["sheets", "net_income", "basic_federal_tax"].index(missing)
    del inputs[index]

    with pytest.raises(MissingArtifactError, match=labels.get(missing, "basic_federal_tax")):
        capability(line).compute(tuple(inputs))


@by_line
def test_has_one_output(line: int) -> None:
    assert len(capability(line).compute(sheets_given(SHEET_A, SHEET_B)).outputs) == 1


# --- trace --------------------------------------------------------------------------------------


def expected_line(
    line: int,
    position: int,
    name: str,
    sheet: Sheet,
    *,
    net_income: str = "100000",
    table: dict[str, dict[int, Decimal]] = EXPECTED,
) -> Any:
    """The trace line of `line` for the sheet `sheet` (named `name`) at `position`, with the
    figures of `table` and the net income given."""
    out = OUTPUTS[line]
    tax, unused, income, surtax, line_3 = (D(figure) for figure in sheet)
    figures = table[name]
    net, basic_tax = D(net_income), D("14500")
    match line:
        case 4:
            return ForeignBusinessLine4(out, position, tax, unused, figures[4])
        case 5:
            return ForeignBusinessLine5(out, position, income, net, basic_tax, CENT, figures[5])
        case 7:
            return ForeignBusinessLine7(out, position, figures[5], surtax, figures[7])
        case 8:
            return ForeignBusinessLine8(out, position, basic_tax, surtax, figures[8])
        case 10:
            return ForeignBusinessLine10(out, position, figures[8], line_3, figures[10])
        case _:
            return ForeignBusinessLine11(
                out, position, figures[4], figures[7], figures[10], figures[11]
            )


@by_line
def test_traces_one_line_per_sheet_then_the_total(line: int) -> None:
    trace = capability(line).compute(sheets_given(SHEET_A, SHEET_B)).trace

    total = EXPECTED["A"][line] + EXPECTED["B"][line]
    assert trace == (
        expected_line(line, 1, "A", SHEET_A),
        expected_line(line, 2, "B", SHEET_B),
        ItemsTotalLine(OUTPUTS[line], ((1, EXPECTED["A"][line]), (2, EXPECTED["B"][line])), total),
    )


@by_line
def test_traces_the_callers_order_with_positions_from_one(line: int) -> None:
    trace = capability(line).compute(sheets_given(SHEET_B, SHEET_C)).trace

    assert trace[:2] == (
        expected_line(line, 1, "B", SHEET_B),
        expected_line(line, 2, "C", SHEET_C),
    )


@by_line
def test_traces_the_line_class_of_its_line(line: int) -> None:
    trace = capability(line).compute(sheets_given(SHEET_A)).trace

    assert type(trace[0]) is BY_LINE[line][2]


@by_line
def test_traces_no_sheets_as_only_an_empty_total(line: int) -> None:
    assert capability(line).compute(sheets_given()).trace == (
        ItemsTotalLine(OUTPUTS[line], (), D("0")),
    )


@by_line
def test_the_last_trace_line_amount_is_the_output(line: int) -> None:
    for rows in ((SHEET_A, SHEET_B), (SHEET_C,), ()):
        result = capability(line).compute(sheets_given(*rows))

        assert result.trace[-1].amount == result.outputs[0].value


@by_line
def test_the_total_is_the_sum_of_its_items(line: int) -> None:
    *_, total_line = capability(line).compute(sheets_given(SHEET_A, SHEET_B, SHEET_E)).trace

    assert isinstance(total_line, ItemsTotalLine)
    assert total_line.total == sum((amount for _, amount in total_line.items), D("0"))


def test_line_5_traces_the_rounding_rule_of_the_dataset() -> None:
    wired = capability(5, rounding(NO_ROUNDING))

    (line, _total) = wired.compute(
        sheets_given(("0", "0", "1", "0", "0"), net_income="8", basic_tax="1")
    ).trace

    assert isinstance(line, ForeignBusinessLine5)
    assert line.rounding == NO_ROUNDING
    assert line.result == D("0.125")


@by_line
def test_compute_is_repeatable(line: int) -> None:
    wired = capability(line)

    assert wired.compute(sheets_given(SHEET_A, SHEET_B)) == wired.compute(
        sheets_given(SHEET_A, SHEET_B)
    )


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[RoundingOnly]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, ROUNDING_ONLY):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(
    line: int, dataset: ParameterDataset[RoundingOnly] | None = None
) -> TaxComputationService:
    dataset = dataset or rounding()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name=f"ca/{BY_LINE[line][1]}",
        params={"rounding": dataset.family},
        consumes={
            "sheets": SHEETS.identifier,
            "net_income": NET_INCOME.identifier,
            "basic_federal_tax": BASIC_TAX.identifier,
        },
        produces={"output": OUTPUTS[line].identifier},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(
            frozenset({SHEETS.identifier, NET_INCOME.identifier, BASIC_TAX.identifier})
        ),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=(OUTPUTS[line].identifier,),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (SHEETS, NET_INCOME, BASIC_TAX, OUTPUTS[line]):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )


@by_line
def test_a_computation_builds_the_capability_from_the_registry_and_its_dataset(line: int) -> None:
    composition = (
        service(line).compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, BY_LINE[line][0])
    assert built.consumes == frozenset({SHEETS, NET_INCOME, BASIC_TAX})
    assert built.produces == frozenset({OUTPUTS[line]})


@by_line
def test_a_computation_gives_the_total_over_the_sheets(line: int) -> None:
    worksheet = service(line).compute(
        JurisdictionCode("CA-ON"), 2025, *sheets_given(SHEET_A, SHEET_B)
    )["ca-on/return"][0]

    assert worksheet.get(OUTPUTS[line]).value == EXPECTED["A"][line] + EXPECTED["B"][line]
    assert isinstance(worksheet.producer_of(OUTPUTS[line]), BY_LINE[line][0])


def test_a_computation_applies_the_datasets_rounding() -> None:
    worksheet = service(5, rounding(NO_ROUNDING)).compute(
        JurisdictionCode("CA-ON"),
        2025,
        *sheets_given(("0", "0", "1", "0", "0"), net_income="8", basic_tax="1"),
    )["ca-on/return"][0]

    assert worksheet.get(OUTPUTS[5]).value == D("0.125")
