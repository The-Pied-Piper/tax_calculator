"""Unit tests for ProvincialForeignTaxCredit, lines 1 to 5 of Form T2036 (ON428 line 82).

Form T2036, "Provincial or Territorial Foreign Tax Credit": "Enter the amount from line 1 of Form
T2209." (line 1); "Enter the amount from line 3 of Form T2209, unless you have to pay minimum
tax.(1)" (line 2); "Line 1 minus line 2" (line 3); "Net foreign non-business income (2)" "×
Provincial or territorial tax otherwise payable (4)" over "Net income (3)" (line 4); "Enter
whichever amount is less: line 3 or line 4." "Provincial or territorial foreign tax credit" (line
5); "Enter the total from line 5 (for each country if applicable) on the line for the provincial or
territorial foreign tax credit of Form 428." Note (2): "Enter the amount reported as net foreign
non-business income from line 2 of Form T2209." Note (3): "Enter the amount reported as net income
from line 2 of Form T2209." And "If you paid tax to more than one foreign country, and the total
of the non-business income taxes that you paid to all foreign countries was more than $200, do the
calculation on a separate form for each country in Canadian dollars."

Its slots: one parameter slot, `rounding` (a `rounding_only` dataset: the rule for line 4); three
consumed slots, `sheets` (the `ca/foreign_tax_credit_sheets` record list of the T2209 sheets, each
record holding line 1 (tax paid), the income used on line 2 and line 3), `net_income` (note 3) and
`provincial_tax` (note 4, the tax otherwise payable), both Decimal; and one produced slot, `total`
(Decimal), the total of line 5 before the form's limit.

Per sheet: line 1 is the sheet's tax paid, line 2 is the sheet's T2209 line 3, line 3 is line 1
minus line 2, line 4 is the sheet's income times the provincial tax over the net income through
`ApplyRatio.ratio_of` (the same object as `core/apply_ratio`), rounded once with the `rounding`
dataset's rule, line 5 is the lesser of line 3 and line 4, and the total is the sum of line 5. No
sheets give 0, and net income is not consulted. A net income of zero or less with at least one
sheet gives line 4 of 0 without a division, so line 5 and the total are 0 (each sheet's income is 0,
the cap floored at 0). It records one `ProvincialForeignTaxCreditLine` per sheet, by position from
1, then an `ItemsTotalLine`; no sheets record the `ItemsTotalLine` alone.

The kinds and dataset families are made up, apart from the sheets, which are the registered record
list.

Line 2 when minimum tax is payable (Form T2036 line 2 "Enter the amount from line 3 of Form T2209,
unless you have to pay minimum tax.(1)", note (1)). Four more consumed slots: `minimum_tax_applies`
(the count `ca/amt_part_5_line_11_is_positive`, int), `non_business_tax_paid` (Form T691 Part 4
line 7, already times 66.6666%), `business_tax_paid` (line 8) and `special_foreign_tax_credit`
(line 11), all but the count Decimal; and two more parameter slots beside `rounding`, `threshold`
(an `amount` dataset, the $200 of the note) and `rate` (a `rate` dataset, the 66.6666% of line 7).
With the count 0, line 2 is the sheet's T2209 line 3 as before and the four figures are not used.
With the count 1 and at least one sheet, line 2 of each sheet is its line 1 times line 11 over a
divisor, worked as an exact fraction and rounded once with the `rounding` dataset's rule: when the
total of the sheets' line 1 is at or under `threshold` (one form), the divisor is that total plus
line 8; when it is over, the divisor is line 7 over `rate` plus line 8. A zero divisor is a
ValidationError naming "line 2 of Form T2036". With the count 1 the sheet's trace line carries the
line 11, the divisor (a ExactFraction) and whether the separate-sheet branch was used, and its
`federal_credit` holds the line 2 used; with the count 0 those fields keep their defaults.

With the count 1, more than one sheet and the total at or under `threshold`, Form T2036 is worked
once on the totals: line 1 is the total tax paid, line 2 is the total times line 11 over the total
plus line 8 (rounded once, held at line 1 within a cent, refused beyond it), line 3 is line 1 less
line 2, line 4 is the total income, capped at net income (0 when net income is zero or less), times
the provincial tax over net income, and line 5 is the lesser. It records one
`PooledProvincialForeignTaxCreditLine` (`sheets` the count, `special_credit` line 11, `divisor` the
ExactFraction of the total plus line 8) and no `ItemsTotalLine`. Over the threshold, and with one
sheet, each sheet is worked on its own as above.
"""

from __future__ import annotations

import decimal
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction as ExactFraction
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca_on.capabilities as ca_on_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capabilities.apply_ratio import ApplyRatio
from tax_engine.domain.capability import CapabilityRegistry, CapabilityResult
from tax_engine.domain.errors import (
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
    ValidationError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.amount import AMOUNT, Amount
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)
from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY, RoundingOnly
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemsTotalLine
from tax_engine.jurisdictions.ca.catalog import (
    FOREIGN_BUSINESS_TAX_PAID,
    FOREIGN_BUSINESS_UNUSED_TAX_CREDITS,
    FOREIGN_NON_BUSINESS_TAX_PAID,
    FOREIGN_SURTAX_OUTSIDE_CANADA,
    FOREIGN_TAX_CREDIT_SHEET_LINE_3,
    FOREIGN_TAX_CREDIT_SHEETS,
    NET_FOREIGN_BUSINESS_INCOME,
    NET_FOREIGN_NON_BUSINESS_INCOME,
)
from tax_engine.jurisdictions.ca_on.capabilities.provincial_foreign_tax_credit import (
    ProvincialForeignTaxCredit,
)
from tax_engine.jurisdictions.ca_on.trace import (
    PooledProvincialForeignTaxCreditLine,
    ProvincialForeignTaxCreditLine,
)
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)

# The return-wide figures and the output come with the wiring; the tests use made-up kinds.
NET_INCOME = ArtifactKind("ex/net_income", Decimal)
PROVINCIAL_TAX = ArtifactKind("ex/provincial_tax", Decimal, non_negative=True)
CREDIT = ArtifactKind("ex/provincial_credit", Decimal, non_negative=True)
SHEETS = FOREIGN_TAX_CREDIT_SHEETS

# A sheet is (line 1 tax paid, income used on line 2, T2209 line 3).
Sheet = tuple[str, str, str]

# Net income 100,000 and provincial tax otherwise payable 5,000: line 4 is 5% of the income.
# US: 1,500 paid, the federal credit 1,400, so line 3 is 100; line 4 is 10,000 x 5% = 500.00.
US: Sheet = ("1500", "10000", "1400")
# UK: 100 paid, all of it credited federally, so line 3 is 0.
UK: Sheet = ("100", "5000", "100")


def rounding(rule: RoundingRule = CENT) -> ParameterDataset[RoundingOnly]:
    """By default half up to the cent."""
    return ParameterDataset(
        "ex/provincial_credit_rounding",
        2025,
        ROUNDING_ONLY,
        RoundingOnly(),
        rule,
        ("https://example.org/rounding",),
    )


MINIMUM_TAX = ArtifactKind("ex/minimum_tax_applies", int, non_negative=True)
LINE_7 = ArtifactKind("ex/non_business_tax_two_thirds", Decimal, non_negative=True)
LINE_8 = ArtifactKind("ex/business_tax_paid", Decimal, non_negative=True)
LINE_11 = ArtifactKind("ex/special_foreign_tax_credit", Decimal, non_negative=True)
RATE_FIGURE = D("0.666666")


def threshold(figure: str = "200") -> ParameterDataset[Amount]:
    """The $200 of note (1), taken as printed."""
    return ParameterDataset(
        "ex/separate_sheet_threshold",
        2025,
        AMOUNT,
        Amount(D(figure)),
        NO_ROUNDING,
        ("https://example.org/threshold",),
    )


def rate() -> ParameterDataset[Rate]:
    """The 66.6666% of Form T691 Part 4 line 7, as printed."""
    return ParameterDataset(
        "ex/two_thirds_rate", 2025, RATE, Rate(RATE_FIGURE), CENT, ("https://example.org/rate",)
    )


def capability(
    dataset: ParameterDataset[RoundingOnly] | None = None,
    limit: ParameterDataset[Amount] | None = None,
) -> ProvincialForeignTaxCredit:
    return ProvincialForeignTaxCredit(
        rounding=dataset or rounding(),
        threshold=limit or threshold(),
        rate=rate(),
        minimum_tax_applies=MINIMUM_TAX,
        sheets=SHEETS,
        net_income=NET_INCOME,
        provincial_tax=PROVINCIAL_TAX,
        non_business_tax_paid=LINE_7,
        business_tax_paid=LINE_8,
        special_foreign_tax_credit=LINE_11,
        total=CREDIT,
    )


def sheet_list(*rows: Sheet) -> Artifact[Any]:
    """A `ca/foreign_tax_credit_sheets` artifact of one record per sheet, in order."""
    records = [
        {
            FOREIGN_NON_BUSINESS_TAX_PAID: D(tax),
            NET_FOREIGN_NON_BUSINESS_INCOME: D(income),
            FOREIGN_TAX_CREDIT_SHEET_LINE_3: D(line_3),
            FOREIGN_BUSINESS_TAX_PAID: D(0),
            FOREIGN_BUSINESS_UNUSED_TAX_CREDITS: D(0),
            NET_FOREIGN_BUSINESS_INCOME: D(0),
            FOREIGN_SURTAX_OUTSIDE_CANADA: D(0),
        }
        for tax, income, line_3 in rows
    ]
    return Artifact(SHEETS, RecordList(SHEETS.fields, records))


def given(
    *rows: Sheet,
    net_income: str = "100000",
    provincial_tax: str = "5000",
    minimum_tax: int = 0,
    line_7: str = "0",
    line_8: str = "0",
    line_11: str = "0",
) -> tuple[Artifact[Any], ...]:
    """The inputs; the minimum tax count is 0 and its figures 0 unless given."""
    return (
        sheet_list(*rows),
        Artifact(NET_INCOME, D(net_income)),
        Artifact(PROVINCIAL_TAX, D(provincial_tax)),
        Artifact(MINIMUM_TAX, minimum_tax),
        Artifact(LINE_7, D(line_7)),
        Artifact(LINE_8, D(line_8)),
        Artifact(LINE_11, D(line_11)),
    )


def totals(result: CapabilityResult) -> Decimal:
    """The `total` output of a computation."""
    (output,) = result.outputs
    assert output.kind == CREDIT
    assert isinstance(output.value, Decimal)
    return output.value


def total(
    *rows: Sheet,
    net_income: str = "100000",
    provincial_tax: str = "5000",
    dataset: ParameterDataset[RoundingOnly] | None = None,
) -> Decimal:
    wired = capability(dataset)
    return totals(wired.compute(given(*rows, net_income=net_income, provincial_tax=provincial_tax)))


def minimum_tax_total(
    *rows: Sheet,
    line_7: str = "0",
    line_8: str = "0",
    line_11: str = "0",
    net_income: str = "100000",
    dataset: ParameterDataset[RoundingOnly] | None = None,
    limit: ParameterDataset[Amount] | None = None,
) -> Decimal:
    """The total with the count 1, net income 100,000 unless given, and provincial tax 5,000."""
    wired = capability(dataset, limit)
    return totals(
        wired.compute(
            given(
                *rows,
                minimum_tax=1,
                line_7=line_7,
                line_8=line_8,
                line_11=line_11,
                net_income=net_income,
            )
        )
    )


def minimum_tax_trace(
    *rows: Sheet,
    line_7: str = "0",
    line_8: str = "0",
    line_11: str = "0",
    net_income: str = "100000",
) -> tuple[Any, ...]:
    """The trace with the count 1, net income 100,000 unless given, and provincial tax 5,000."""
    wired = capability()
    return wired.compute(
        given(
            *rows,
            minimum_tax=1,
            line_7=line_7,
            line_8=line_8,
            line_11=line_11,
            net_income=net_income,
        )
    ).trace


# --- contract and wiring ------------------------------------------------------------------------


def test_is_registered_as_ca_on_provincial_foreign_tax_credit() -> None:
    assert (
        CapabilityRegistry.shared().get("ca-on/provincial_foreign_tax_credit")
        is ProvincialForeignTaxCredit
    )


def test_is_exported_from_the_ca_on_capabilities_package() -> None:
    assert ca_on_capabilities.NAMESPACE == "ca-on"
    assert "provincial_foreign_tax_credit" in ca_on_capabilities.__all__
    assert (
        ca_on_capabilities.provincial_foreign_tax_credit.ProvincialForeignTaxCredit
        is ProvincialForeignTaxCredit
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset(
        {SHEETS, NET_INCOME, PROVINCIAL_TAX, MINIMUM_TAX, LINE_7, LINE_8, LINE_11}
    )
    assert capability().produces == frozenset({CREDIT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ProvincialForeignTaxCredit)
    assert "produces" not in vars(ProvincialForeignTaxCredit)


def test_declares_its_slots() -> None:
    assert ProvincialForeignTaxCredit.PARAMETERS == {
        "rounding": ROUNDING_ONLY,
        "threshold": AMOUNT,
        "rate": RATE,
    }
    assert ProvincialForeignTaxCredit.CONSUMES == {
        "sheets": RecordList,
        "net_income": Decimal,
        "provincial_tax": Decimal,
        "minimum_tax_applies": int,
        "non_business_tax_paid": Decimal,
        "business_tax_paid": Decimal,
        "special_foreign_tax_credit": Decimal,
    }
    assert ProvincialForeignTaxCredit.PRODUCES == {"total": Decimal}
    assert not ProvincialForeignTaxCredit.is_list_slot("sheets")


def test_its_slots_are_read_only() -> None:
    slots = (
        ProvincialForeignTaxCredit.PARAMETERS,
        ProvincialForeignTaxCredit.CONSUMES,
        ProvincialForeignTaxCredit.PRODUCES,
    )
    for each in slots:
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(ProvincialForeignTaxCredit.CONSUMES, Mapping[str, type])
    assert_type(ProvincialForeignTaxCredit.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    assert totals(capability().compute(given(US))) == D("100")


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        ProvincialForeignTaxCredit(  # type: ignore[call-arg]
            rounding=rounding(),
            threshold=threshold(),
            rate=rate(),
            minimum_tax_applies=MINIMUM_TAX,
            sheets=SHEETS,
            net_income=NET_INCOME,
            provincial_tax=PROVINCIAL_TAX,
            non_business_tax_paid=LINE_7,
            business_tax_paid=LINE_8,
            special_foreign_tax_credit=LINE_11,
            total=CREDIT,
            extra=CENT,
        )


def test_rejects_a_money_kind_for_its_sheets() -> None:
    with pytest.raises(InvalidCapabilityError, match="ProvincialForeignTaxCredit.*'sheets'"):
        ProvincialForeignTaxCredit(
            rounding=rounding(),
            threshold=threshold(),
            rate=rate(),
            minimum_tax_applies=MINIMUM_TAX,
            sheets=CREDIT,  # type: ignore[arg-type]
            net_income=NET_INCOME,
            provincial_tax=PROVINCIAL_TAX,
            non_business_tax_paid=LINE_7,
            business_tax_paid=LINE_8,
            special_foreign_tax_credit=LINE_11,
            total=CREDIT,
        )


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        amount = ParameterDataset(
            "ex/some_amount", 2025, AMOUNT, Amount(D("5")), NO_ROUNDING, ("https://example.org/a",)
        )
        ProvincialForeignTaxCredit(
            rounding=amount,  # type: ignore[arg-type]
            threshold=threshold(),
            rate=rate(),
            minimum_tax_applies=MINIMUM_TAX,
            sheets=SHEETS,
            net_income=NET_INCOME,
            provincial_tax=PROVINCIAL_TAX,
            non_business_tax_paid=LINE_7,
            business_tax_paid=LINE_8,
            special_foreign_tax_credit=LINE_11,
            total=CREDIT,
        )

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(ProvincialForeignTaxCredit, "__type_params__", ())
    assert not getattr(ProvincialForeignTaxCredit, "__parameters__", ())


# --- computing: lines 1 to 5 --------------------------------------------------------------------


def test_one_sheet_gives_the_lesser_of_line_3_and_line_4() -> None:
    # Line 3 = 1,500 - 1,400 = 100; line 4 = 10,000 x 5,000 / 100,000 = 500.00; line 5 = 100.
    assert total(US) == D("100")


def test_a_sheet_whose_line_4_is_below_line_3_gives_line_4() -> None:
    # Line 3 = 1,500 - 0 = 1,500; line 4 = 500.00.
    assert total(("1500", "10000", "0")) == D("500.00")


def test_a_sheet_credited_in_full_federally_adds_nothing() -> None:
    # Line 3 = 100 - 100 = 0; line 4 = 5,000 x 5% = 250.00.
    assert total(UK) == D("0")


def test_the_total_is_the_sum_of_line_5_of_each_sheet() -> None:
    # US 100 + a second sheet of line 3 = 300 - 100 = 200 and line 4 = 5,000 x 5% = 250.00: 200.
    assert total(US, ("300", "5000", "100")) == D("300")


def test_each_sheets_line_5_is_the_lesser_of_its_own_lines_3_and_4() -> None:
    # 800 - 0 = 800 against 500.00 gives 500.00; 100 - 0 = 100 against 250.00 gives 100.
    assert total(("800", "10000", "0"), ("100", "5000", "0")) == D("600.00")


def test_the_total_does_not_depend_on_the_order_of_the_sheets() -> None:
    assert total(UK, US) == total(US, UK)


def test_line_3_is_line_1_minus_line_2() -> None:
    # Line 3 = 1,500 - 1,400 = 100, not the sheet's own line 3 of 1,400.
    assert total(("1500", "100000", "1400")) == D("100")


def test_a_sheet_with_no_income_adds_nothing() -> None:
    assert total(("500", "0", "0")) == D("0.00")


def test_a_zero_provincial_tax_gives_zero() -> None:
    assert total(("1500", "10000", "0"), provincial_tax="0") == D("0.00")


def test_cents_in_the_tax_paid_are_kept() -> None:
    # Line 3 = 1,234.56 - 1,000 = 234.56, below line 4 = 100,000 x 5% = 5,000.00.
    assert total(("1234.56", "100000", "1000")) == D("234.56")


def test_line_3_depends_on_both_the_tax_paid_and_the_t2209_line_3() -> None:
    # 1,500 - 1,400 and 1,400 - 1,300 are both 100, while 1,500 - 1,300 is 200 (line 4 is 500.00).
    assert total(("1500", "10000", "1400")) == D("100")
    assert total(("1400", "10000", "1300")) == D("100")
    assert total(("1500", "10000", "1300")) == D("200")


# --- computing: no sheets ------------------------------------------------------------------------


def test_no_sheets_give_zero() -> None:
    output = Artifact(CREDIT, totals(capability().compute(given())))

    assert output == Artifact(CREDIT, D("0"))
    assert type(output.value) is Decimal
    assert not output.value.is_signed()


def test_no_sheets_do_not_consult_net_income() -> None:
    assert total(net_income="0") == D("0")


def test_no_sheets_do_not_consult_a_negative_net_income() -> None:
    assert total(net_income="-1") == D("0")


def test_no_sheets_need_neither_net_income_nor_provincial_tax_to_be_given() -> None:
    result = capability().compute((sheet_list(), Artifact(MINIMUM_TAX, 0)))

    assert totals(result) == D("0")


# --- computing: net income zero or less ---------------------------------------------------------

# A net income of zero or less gives line 4 of 0 without a division, so line 5 is 0 whatever line 3
# is. Line 3 (line 1 less the sheet's T2209 line 3) does not read the net income and is unchanged.
ZERO_OR_LESS_NET_INCOMES = pytest.mark.parametrize("net_income", ["0", "-1", "-13010"])


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_a_credit_of_zero(net_income: str) -> None:
    assert total(US, net_income=net_income) == D("0")


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_zero_with_several_sheets(net_income: str) -> None:
    assert total(US, UK, net_income=net_income) == D("0")


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_traces_each_sheet_with_zero_income_and_lines_4_and_5(
    net_income: str,
) -> None:
    trace = capability().compute(given(US, UK, net_income=net_income)).trace

    assert trace == (
        sheet_line(1, "1500", "1400", "100", "0", "0", "0", net=net_income),
        sheet_line(2, "100", "100", "0", "0", "0", "0", net=net_income),
        ItemsTotalLine(CREDIT, ((1, D("0")), (2, D("0"))), D("0")),
    )


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_zero_with_the_minimum_tax_line_2(
    net_income: str,
) -> None:
    # Line 2 is 150 x 80 / (150 + 50) = 60.00 without a net income, so line 3 is 90.00; line 4 is
    # 0 and so is line 5.
    assert minimum_tax_total(
        ("150", "10000", "1400"),
        line_7="100",
        line_8="50",
        line_11="80",
        net_income=net_income,
    ) == D("0")


def test_a_zero_net_income_is_worked_on_a_wired_capability_without_changing_it() -> None:
    wired = capability()

    assert totals(wired.compute(given(US, net_income="0"))) == D("0")

    assert totals(wired.compute(given(US))) == D("100")


@ZERO_OR_LESS_NET_INCOMES
def test_a_computation_gives_a_credit_of_zero_for_a_net_income_of_zero_or_less(
    net_income: str,
) -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, *given(US, UK, net_income=net_income)
    )["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("0")
    assert worksheet.trace[-1].amount == D("0")


# --- computing: rounding -------------------------------------------------------------------------


def test_line_4_is_rounded_half_up_to_the_cent() -> None:
    # 10 x 100 / 300 = 3.333...; 20 x 100 / 300 = 6.666...
    assert total(("50", "10", "0"), net_income="300", provincial_tax="100") == D("3.33")
    assert total(("50", "20", "0"), net_income="300", provincial_tax="100") == D("6.67")


def test_a_tie_rounds_half_up_by_the_dataset_rule() -> None:
    # 0.015 x 1 / 3 is exactly 0.005: half up gives 0.01, half even 0.00. Dividing first would
    # give 0.00499... and round down.
    assert total(("5", "0.015", "0"), net_income="3", provincial_tax="1") == D("0.01")
    half_even = RoundTo(D("0.01"), RoundingMode.HALF_EVEN)
    assert total(
        ("5", "0.015", "0"), net_income="3", provincial_tax="1", dataset=rounding(half_even)
    ) == D("0.00")


def test_each_sheet_is_rounded_before_the_sheets_are_summed() -> None:
    # Three sheets of 100 income, x 100 / 300: 33.33 x 3 = 99.99, not the rounded exact 100.00.
    rows = (("300", "100", "0"), ("300", "100", "0"), ("300", "100", "0"))

    assert total(*rows, net_income="300", provincial_tax="100") == D("99.99")


def test_a_whole_dollar_rule_rounds_each_sheet_to_the_dollar() -> None:
    whole = RoundTo(D("1"), RoundingMode.FLOOR)

    # 10 / 3 = 3.33 floors to 3; 20 / 3 = 6.67 floors to 6.
    assert total(
        ("300", "10", "0"),
        ("300", "20", "0"),
        net_income="300",
        provincial_tax="100",
        dataset=rounding(whole),
    ) == D("9")


def test_no_rounding_keeps_an_exact_finite_quotient() -> None:
    # 0.015 x 1 / 2 = 0.0075.
    assert total(
        ("5", "0.015", "0"), net_income="2", provincial_tax="1", dataset=rounding(NO_ROUNDING)
    ) == D("0.0075")


def test_no_rounding_refuses_a_quotient_with_no_finite_expansion() -> None:
    with pytest.raises(decimal.Inexact):
        total(
            ("5", "10", "0"), net_income="300", provincial_tax="100", dataset=rounding(NO_ROUNDING)
        )


def test_a_rounded_line_4_carries_the_increments_scale() -> None:
    assert str(total(("1500", "10000", "0"))) == "500.00"


# --- computing: the shared ratio object ---------------------------------------------------------


def test_line_4_is_worked_by_the_shared_ratio_method_of_apply_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ApplyRatio.ratio_of
    calls: list[tuple[Decimal, Decimal, Decimal, RoundingRule]] = []

    def spy(
        amount: Decimal, numerator: Decimal, denominator: Decimal, rule: RoundingRule
    ) -> Decimal:
        calls.append((amount, numerator, denominator, rule))
        return original(amount, numerator, denominator, rule)

    monkeypatch.setattr(ApplyRatio, "ratio_of", staticmethod(spy))

    assert total(US, UK) == D("100")
    # amount = the sheet's income, numerator = the provincial tax, denominator = net income.
    assert calls == [
        (D("10000"), D("5000"), D("100000"), CENT),
        (D("5000"), D("5000"), D("100000"), CENT),
    ]


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(CREDIT, D("9"))

    result = capability().compute((other, *given(US)))

    assert totals(result) == D("100")


@pytest.mark.parametrize(
    "missing",
    [
        "foreign_tax_credit_sheets",
        "net_income",
        "provincial_tax",
        "minimum_tax_applies",
        "non_business_tax_paid",
        "business_tax_paid",
        "special_foreign_tax_credit",
    ],
)
def test_a_missing_input_is_a_missing_artifact(missing: str) -> None:
    absent = LINE_7.identifier if missing == "non_business_tax_paid" else missing
    inputs = [a for a in given(US) if not a.kind.identifier.endswith(absent)]

    with pytest.raises(MissingArtifactError, match=absent.split("/")[-1]):
        capability().compute(tuple(inputs))


def test_has_one_output_the_total() -> None:
    result = capability().compute(given(US, UK))

    assert [a.kind for a in result.outputs] == [CREDIT]


# --- trace ---------------------------------------------------------------------------------------


def sheet_line(
    position: int,
    tax: str,
    federal: str,
    line_3: str,
    income: str,
    line_4: str,
    result: str,
    rule: RoundingRule = CENT,
    net: str = "100000",
) -> Any:
    return ProvincialForeignTaxCreditLine(
        output=CREDIT,
        position=position,
        tax_paid=D(tax),
        federal_credit=D(federal),
        line_3=D(line_3),
        income=D(income),
        net_income=D(net),
        provincial_tax=D("5000"),
        rounding=rule,
        line_4=D(line_4),
        result=D(result),
    )


def test_traces_one_line_per_sheet_then_the_total() -> None:
    trace = capability().compute(given(US, UK)).trace

    assert trace == (
        sheet_line(1, "1500", "1400", "100", "10000", "500.00", "100"),
        sheet_line(2, "100", "100", "0", "5000", "250.00", "0"),
        ItemsTotalLine(CREDIT, ((1, D("100")), (2, D("0"))), D("100")),
    )


def test_traces_the_callers_order_with_positions_from_one() -> None:
    trace = capability().compute(given(UK, US)).trace

    assert trace == (
        sheet_line(1, "100", "100", "0", "5000", "250.00", "0"),
        sheet_line(2, "1500", "1400", "100", "10000", "500.00", "100"),
        ItemsTotalLine(CREDIT, ((1, D("0")), (2, D("100"))), D("100")),
    )


def test_traces_a_single_sheet_as_one_line_and_a_total() -> None:
    trace = capability().compute(given(("1500", "10000", "0"))).trace

    assert trace == (
        sheet_line(1, "1500", "0", "1500", "10000", "500.00", "500.00"),
        ItemsTotalLine(CREDIT, ((1, D("500.00")),), D("500.00")),
    )


def test_traces_no_sheets_as_only_an_empty_total() -> None:
    assert capability().compute(given()).trace == (ItemsTotalLine(CREDIT, (), D("0")),)


def test_traces_the_rounding_rule_of_the_dataset() -> None:
    wired = capability(rounding(NO_ROUNDING))

    line, _total = wired.compute(
        given(("5", "0.015", "0"), net_income="2", provincial_tax="1")
    ).trace

    assert isinstance(line, ProvincialForeignTaxCreditLine)
    assert line.rounding == NO_ROUNDING
    assert line.line_4 == D("0.0075")


def test_the_last_trace_line_amount_is_the_output() -> None:
    for rows in ((US, UK), (US,), ()):
        result = capability().compute(given(*rows))

        assert result.trace[-1].amount == totals(result)


def test_the_total_is_the_sum_of_its_items() -> None:
    *_, total_line = capability().compute(given(US, UK, ("1500", "10000", "0"))).trace

    assert isinstance(total_line, ItemsTotalLine)
    assert total_line.total == sum((amount for _, amount in total_line.items), D("0"))


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(given(US, UK)) == wired.compute(given(US, UK))


# --- line 2 when minimum tax is payable: the count ----------------------------------------------


def test_the_count_0_keeps_line_2_as_the_t2209_line_3_whatever_the_minimum_tax_figures() -> None:
    result = capability().compute(
        given(US, UK, minimum_tax=0, line_7="400", line_8="100", line_11="90")
    )

    assert totals(result) == D("100")
    assert result.trace == capability().compute(given(US, UK)).trace


def test_the_count_0_trace_lines_keep_the_default_minimum_tax_fields() -> None:
    line, *_ = capability().compute(given(US, line_11="90")).trace

    assert isinstance(line, ProvincialForeignTaxCreditLine)
    assert line.special_credit is None
    assert line.divisor is None
    assert line.separate_sheet is False


def test_the_count_1_replaces_line_2_with_the_share_of_the_special_foreign_tax_credit() -> None:
    # The sheet's T2209 line 3 of 1,400 is not used: line 2 = 150 x 80 / (150 + 50) = 60.00,
    # line 3 = 150 - 60 = 90.00, line 4 = 500.00, line 5 = 90.00.
    assert minimum_tax_total(
        ("150", "10000", "1400"), line_7="100", line_8="50", line_11="80"
    ) == D("90.00")


def test_the_count_1_with_no_sheets_gives_zero_and_refuses_nothing() -> None:
    assert minimum_tax_total() == D("0")
    assert minimum_tax_total(line_7="0", line_8="0", line_11="0") == D("0")


# --- line 2 when minimum tax is payable: one form (the total at or under the threshold) -----------


def test_one_sheet_under_the_threshold_uses_the_total_of_line_1_plus_line_8() -> None:
    # Line 7 of 400 is more than 200 but is not the test: the sheets' line 1 total, 150, is.
    # Line 2 = 150 x 80 / (150 + 50) = 60.00; line 3 = 90.00; line 4 = 500.00.
    assert minimum_tax_total(
        ("150", "10000", "1400"), line_7="400", line_8="50", line_11="80"
    ) == D("90.00")


def test_one_sheet_exactly_at_the_threshold_is_the_one_form_branch() -> None:
    # 200 is "$200 or less". Line 2 = 200 x 90 / (200 + 100) = 60.00; line 3 = 140.00.
    # The separate-sheet divisor would be 100 / 0.666666 + 100 = 250.00015 and line 2 72.00.
    assert minimum_tax_total(
        ("200", "10000", "1400"), line_7="100", line_8="100", line_11="90"
    ) == D("140.00")


def test_one_sheet_a_cent_over_the_threshold_is_the_separate_sheet_branch() -> None:
    # Line 2 = 200.01 x 90 / (100 / 0.666666 + 100) = 72.00 (the one-form figure is 60.00);
    # line 3 = 200.01 - 72.00 = 128.01.
    assert minimum_tax_total(
        ("200.01", "10000", "1400"), line_7="100", line_8="100", line_11="90"
    ) == D("128.01")


def test_two_sheets_at_the_threshold_are_one_form_worked_on_the_total() -> None:
    # Total 120 + 80 = 200 is "$200 or less", so Form T2036 is one form on the totals: line 2 =
    # 200 x 90 / (200 + 100) = 60.00; line 3 = 140.00. Line 4 = 15000 x 5000 / 100000 = 750.00,
    # line 5 = 140.00. Not per sheet (120 x 90 / 300 = 36.00 and 80 x 90 / 300 = 24.00).
    rows = (("120", "10000", "0"), ("80", "5000", "0"))

    assert minimum_tax_total(*rows, line_7="400", line_8="100", line_11="90") == D("140.00")
    assert minimum_tax_trace(*rows, line_7="400", line_8="100", line_11="90") == (
        pooled_minimum_line(2, "200", "60.00", "140.00", "15000", "750.00", "140.00", "90", 300),
    )


def test_two_sheets_under_the_threshold_are_one_form_worked_on_the_total() -> None:
    # Total 100 + 50 = 150 is one form: line 2 = 150 x 80 / (150 + 50) = 60.00; line 3 = 90.00.
    assert minimum_tax_total(
        ("100", "10000", "0"), ("50", "5000", "0"), line_7="0", line_8="50", line_11="80"
    ) == D("90.00")
    assert minimum_tax_trace(
        ("100", "10000", "0"), ("50", "5000", "0"), line_7="0", line_8="50", line_11="80"
    ) == (pooled_minimum_line(2, "150", "60.00", "90.00", "15000", "750.00", "90.00", "80", 200),)


def test_pooled_line_2_is_rounded_once_on_the_total_not_per_sheet() -> None:
    # Total 150, divisor 150 + 100 = 250, line 11 1.01. Line 2 on the total = 150 x 1.01 / 250 =
    # 0.606, half-up 0.61; line 3 = 149.39. Per sheet it would be 100 x 1.01 / 250 = 0.404, 0.40,
    # and 50 x 1.01 / 250 = 0.202, 0.20: 0.60 in all, so line 3 would be 149.40.
    rows = (("100", "10000", "0"), ("50", "5000", "0"))

    assert minimum_tax_total(*rows, line_8="100", line_11="1.01") == D("149.39")
    assert minimum_tax_trace(*rows, line_8="100", line_11="1.01") == (
        pooled_minimum_line(2, "150", "0.61", "149.39", "15000", "750.00", "149.39", "1.01", 250),
    )


def test_the_one_form_branch_does_not_use_line_7_or_the_rate() -> None:
    low = minimum_tax_total(("150", "10000", "0"), line_7="1", line_8="50", line_11="80")
    high = minimum_tax_total(("150", "10000", "0"), line_7="9999", line_8="50", line_11="80")

    assert low == high == D("90.00")


# --- line 2 when minimum tax is payable: a form for each country (the total over the threshold) ---


def test_one_sheet_over_the_threshold_divides_by_line_7_over_the_rate_plus_line_8() -> None:
    # Divisor = 200 / 0.666666 + 100 = 400.0003000003...; line 2 = 300 x 250 / divisor =
    # 187.49985937... = 187.50; line 3 = 112.50; line 4 = 500.00; line 5 = 112.50.
    assert minimum_tax_total(
        ("300", "10000", "1400"), line_7="200", line_8="100", line_11="250"
    ) == D("112.50")


def test_two_sheets_over_the_threshold_each_take_their_own_line_1_over_the_one_divisor() -> None:
    # Divisor = 666.666 / 0.666666 + 0 = 1,000; line 2 = 300 x 250 / 1,000 = 75.00 and
    # 200 x 250 / 1,000 = 50.00; line 3 = 225.00 and 150.00; line 4 = 500.00 and 250.00.
    assert minimum_tax_total(
        ("300", "10000", "0"), ("200", "5000", "0"), line_7="666.666", line_8="0", line_11="250"
    ) == D("375.00")


def test_line_8_is_added_to_the_divisor_in_the_separate_sheet_branch() -> None:
    # Divisor = 666.666 / 0.666666 + 1,000 = 2,000; line 2 = 300 x 250 / 2,000 = 37.50 and
    # 200 x 250 / 2,000 = 25.00; line 3 = 262.50 and 175.00.
    assert minimum_tax_total(
        ("300", "10000", "0"), ("200", "5000", "0"), line_7="666.666", line_8="1000", line_11="250"
    ) == D("437.50")


# --- line 2 when minimum tax is payable: the threshold and the rate are the datasets' -------------


def test_the_threshold_is_the_datasets_figure() -> None:
    sheet = ("250", "10000", "0")

    # With 300 as the figure 250 is at or under it (one form: 250 x 100 / 250 = 100.00, line 3
    # 150.00); with the printed 200 it is over it (separate: line 7 100.01 gives line 2 166.65).
    assert minimum_tax_total(
        sheet, line_7="100.01", line_8="0", line_11="100", limit=threshold("300")
    ) == D("150.00")
    assert minimum_tax_total(sheet, line_7="100.01", line_8="0", line_11="100") == D("83.35")


def test_the_rate_is_the_datasets_figure() -> None:
    half = ParameterDataset(
        "ex/half_rate", 2025, RATE, Rate(D("0.5")), CENT, ("https://example.org/rate",)
    )
    wired = ProvincialForeignTaxCredit(
        rounding=rounding(),
        threshold=threshold(),
        rate=half,
        minimum_tax_applies=MINIMUM_TAX,
        sheets=SHEETS,
        net_income=NET_INCOME,
        provincial_tax=PROVINCIAL_TAX,
        non_business_tax_paid=LINE_7,
        business_tax_paid=LINE_8,
        special_foreign_tax_credit=LINE_11,
        total=CREDIT,
    )

    # Divisor = 300 / 0.5 + 0 = 600; line 2 = 300 x 120 / 600 = 60.00; line 3 = 240.00.
    result = wired.compute(
        given(("300", "100000", "0"), minimum_tax=1, line_7="300", line_8="0", line_11="120")
    )

    assert totals(result) == D("240.00")


# --- line 2 when minimum tax is payable: exact fraction, one rounding -----------------------------


def test_the_divisor_is_not_rounded_before_line_2_is_worked() -> None:
    # Divisor = 100.01 / 0.666666 = 150.015150...; line 2 = 250 x 100 / divisor = 166.65 (a divisor
    # rounded to the cent, 150.02, would give 166.64); line 3 = 83.35.
    assert minimum_tax_total(
        ("250", "10000", "0"), line_7="100.01", line_8="0", line_11="100"
    ) == D("83.35")


def test_line_2_is_rounded_half_up_to_the_cent_once() -> None:
    # 1 x 0.02 / (1 + 3) = 0.005 exactly: half up gives 0.01 (line 3 0.99), half even 0.00 (1.00).
    sheet = ("1", "10000", "0")

    assert minimum_tax_total(sheet, line_8="3", line_11="0.02") == D("0.99")
    half_even = RoundTo(D("0.01"), RoundingMode.HALF_EVEN)
    assert minimum_tax_total(sheet, line_8="3", line_11="0.02", dataset=rounding(half_even)) == D(
        "1.00"
    )


def test_line_2_is_rounded_with_the_rounding_dataset() -> None:
    whole = RoundTo(D("1"), RoundingMode.FLOOR)

    # Line 2 = 100 x 70 / 300 = 23.33 floors to 23; line 3 = 77.
    assert minimum_tax_total(
        ("100", "10000", "0"), line_8="200", line_11="70", dataset=rounding(whole)
    ) == D("77")


def test_a_rule_that_keeps_every_place_refuses_a_line_2_with_no_finite_expansion() -> None:
    with pytest.raises(decimal.Inexact):
        minimum_tax_total(
            ("100", "10000", "0"), line_8="200", line_11="70", dataset=rounding(NO_ROUNDING)
        )


# --- line 2 when minimum tax is payable: a zero divisor -------------------------------------------


def test_no_tax_paid_and_no_line_8_is_a_zero_divisor_and_refused() -> None:
    with pytest.raises(ValidationError, match="line 2 of Form T2036"):
        minimum_tax_total(("0", "10000", "0"), line_8="0", line_11="0")


def test_no_tax_paid_on_several_sheets_and_no_line_8_is_refused() -> None:
    with pytest.raises(ValidationError, match="line 2 of Form T2036"):
        minimum_tax_total(("0", "10000", "0"), ("0", "5000", "0"), line_11="0")


def test_a_zero_line_7_and_line_8_over_the_threshold_is_refused() -> None:
    with pytest.raises(ValidationError, match="line 2 of Form T2036"):
        minimum_tax_total(("300", "10000", "0"), line_7="0", line_8="0", line_11="0")


def test_a_zero_divisor_is_not_refused_with_the_count_0() -> None:
    assert totals(capability().compute(given(("0", "10000", "0")))) == D("0")


def test_a_zero_tax_paid_is_not_refused_when_line_8_makes_the_divisor_positive() -> None:
    assert minimum_tax_total(("0", "10000", "0"), line_8="10", line_11="5") == D("0.00")


# --- line 2 when minimum tax is payable: line 4 is unchanged ----------------------------


def test_the_minimum_tax_line_2_leaves_line_4_to_the_shared_ratio_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ApplyRatio.ratio_of
    calls: list[tuple[Decimal, Decimal, Decimal, RoundingRule]] = []

    def spy(
        amount: Decimal, numerator: Decimal, denominator: Decimal, rule: RoundingRule
    ) -> Decimal:
        calls.append((amount, numerator, denominator, rule))
        return original(amount, numerator, denominator, rule)

    monkeypatch.setattr(ApplyRatio, "ratio_of", staticmethod(spy))

    minimum_tax_total(("150", "10000", "0"), line_8="50", line_11="80")

    assert (D("10000"), D("5000"), D("100000"), CENT) in calls


# --- line 2 when minimum tax is payable: trace ---------------------------------------------------


def minimum_line(
    position: int,
    tax: str,
    line_2: str,
    line_3: str,
    income: str,
    line_4: str,
    result: str,
    line_11: str,
    divisor: ExactFraction,
    separate: bool,
) -> Any:
    return ProvincialForeignTaxCreditLine(
        output=CREDIT,
        position=position,
        tax_paid=D(tax),
        federal_credit=D(line_2),
        line_3=D(line_3),
        income=D(income),
        net_income=D("100000"),
        provincial_tax=D("5000"),
        rounding=CENT,
        line_4=D(line_4),
        result=D(result),
        special_credit=D(line_11),
        divisor=divisor,
        separate_sheet=separate,
    )


def pooled_minimum_line(
    sheets: int,
    tax: str,
    line_2: str,
    line_3: str,
    income: str,
    line_4: str,
    result: str,
    line_11: str,
    divisor: int,
    net: str = "100000",
) -> Any:
    """The one pooled line of the count 1 one-form branch, net income 100,000 and tax 5,000 unless
    given; `divisor` is the total plus line 8 as a whole number."""
    return PooledProvincialForeignTaxCreditLine(
        output=CREDIT,
        sheets=sheets,
        tax_paid=D(tax),
        federal_credit=D(line_2),
        line_3=D(line_3),
        income=D(income),
        net_income=D(net),
        provincial_tax=D("5000"),
        threshold=D("200"),
        rounding=CENT,
        line_4=D(line_4),
        result=D(result),
        special_credit=D(line_11),
        divisor=ExactFraction(divisor),
    )


def test_traces_the_one_form_line_2_with_its_divisor() -> None:
    # One pooled line, no ItemsTotalLine: tax 200 (120 + 80), line 2 = 200 x 90 / 300 = 60.00, line
    # 3 = 140.00, income 15000, line 4 = 750.00, result 140.00, divisor 300 (200 + 100).
    trace = minimum_tax_trace(
        ("120", "10000", "1400"),
        ("80", "5000", "0"),
        line_7="400",
        line_8="100",
        line_11="90",
    )

    assert trace == (
        pooled_minimum_line(2, "200", "60.00", "140.00", "15000", "750.00", "140.00", "90", 300),
    )


def test_traces_the_separate_sheet_line_2_with_its_exact_divisor() -> None:
    trace = (
        capability()
        .compute(
            given(
                ("300", "10000", "0"),
                ("200", "5000", "0"),
                minimum_tax=1,
                line_7="666.666",
                line_8="0",
                line_11="250",
            )
        )
        .trace
    )

    divisor = ExactFraction(D("666.666")) / ExactFraction(RATE_FIGURE)
    assert divisor == 1000
    assert trace == (
        minimum_line(
            1, "300", "75.00", "225.00", "10000", "500.00", "225.00", "250", divisor, True
        ),
        minimum_line(2, "200", "50.00", "150.00", "5000", "250.00", "150.00", "250", divisor, True),
        ItemsTotalLine(CREDIT, ((1, D("225.00")), (2, D("150.00"))), D("375.00")),
    )


def test_the_traced_separate_sheet_divisor_is_the_unrounded_fraction() -> None:
    line, _total = (
        capability()
        .compute(
            given(("250", "10000", "0"), minimum_tax=1, line_7="100.01", line_8="0", line_11="100")
        )
        .trace
    )

    assert isinstance(line, ProvincialForeignTaxCreditLine)
    assert line.divisor == ExactFraction(D("100.01")) / ExactFraction(RATE_FIGURE)
    assert line.federal_credit == D("166.65")
    assert line.separate_sheet is True


def test_the_minimum_tax_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute(
        given(("150", "10000", "0"), minimum_tax=1, line_8="50", line_11="80")
    )

    assert result.trace[-1].amount == totals(result) == D("90.00")


def test_the_pooled_one_form_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute(
        given(
            ("100", "10000", "0"),
            ("50", "5000", "0"),
            minimum_tax=1,
            line_8="50",
            line_11="80",
        )
    )

    assert result.trace[-1].amount == totals(result) == D("90.00")
    assert not [line for line in result.trace if isinstance(line, ItemsTotalLine)]


def test_the_pooled_one_form_income_is_capped_at_net_income() -> None:
    # Total income 10000 + 5000 = 15000 is more than net income 12000, so the income is 12000:
    # line 4 = 12000 x 5000 / 12000 = 5000.00 (uncapped it would be 6250.00); line 5 is still the
    # lesser of line 3 (90.00) and line 4, 90.00.
    rows = (("100", "10000", "0"), ("50", "5000", "0"))

    assert minimum_tax_trace(*rows, line_8="50", line_11="80", net_income="12000") == (
        pooled_minimum_line(
            2, "150", "60.00", "90.00", "12000", "5000.00", "90.00", "80", 200, "12000"
        ),
    )
    assert minimum_tax_total(*rows, line_8="50", line_11="80", net_income="12000") == D("90.00")


@pytest.mark.parametrize("net_income", ["0", "-1"])
def test_a_pooled_one_form_with_net_income_of_zero_or_less_gives_zero(net_income: str) -> None:
    # Line 4 is 0 without a division (the income is 0 when net income is not positive), so line 5
    # is 0 whatever line 3 is; line 3 is 150 - 60.00 = 90.00 and does not read net income.
    rows = (("100", "10000", "0"), ("50", "5000", "0"))

    assert minimum_tax_total(*rows, line_8="50", line_11="80", net_income=net_income) == D("0")
    assert minimum_tax_trace(*rows, line_8="50", line_11="80", net_income=net_income) == (
        pooled_minimum_line(2, "150", "60.00", "90.00", "0", "0", "0", "80", 200, net_income),
    )


def test_a_pooled_line_2_a_cent_above_line_1_is_held_at_line_1() -> None:
    # Total 150, divisor 150 + 0 = 150, line 11 150.01: line 2 = 150 x 150.01 / 150 = 150.01, a
    # cent over line 1, so it is held at 150.00; line 3 = 0.00 and so is the result.
    rows = (("100", "10000", "0"), ("50", "5000", "0"))

    assert minimum_tax_total(*rows, line_8="0", line_11="150.01") == D("0")
    assert minimum_tax_trace(*rows, line_8="0", line_11="150.01") == (
        pooled_minimum_line(2, "150", "150.00", "0.00", "15000", "750.00", "0.00", "150.01", 150),
    )


def test_a_pooled_line_2_more_than_a_cent_above_line_1_is_refused() -> None:
    rows = (("100", "10000", "0"), ("50", "5000", "0"))

    with pytest.raises(
        ValidationError,
        match=r"line 2 of Form T2036, 150\.02, is more than the 150 of its line 1",
    ):
        minimum_tax_total(*rows, line_8="0", line_11="150.02")


def test_a_pooled_zero_divisor_with_several_sheets_is_refused_with_the_total_message() -> None:
    with pytest.raises(
        ValidationError,
        match="the total of tax paid plus the business tax is zero, so line 2 of Form T2036",
    ):
        minimum_tax_total(("0", "10000", "0"), ("0", "5000", "0"), line_8="0", line_11="0")


def test_a_pooled_one_form_is_not_worked_when_the_total_is_over_the_threshold() -> None:
    # Total 300 + 200 = 500 is over 200: each sheet is worked on its own, separate sheet, and no
    # pooled line is recorded.
    trace = minimum_tax_trace(
        ("300", "10000", "0"), ("200", "5000", "0"), line_7="666.666", line_8="0", line_11="250"
    )

    assert not [line for line in trace if isinstance(line, PooledProvincialForeignTaxCreditLine)]
    assert [line.separate_sheet for line in trace[:-1]] == [True, True]


def test_a_count_0_with_several_sheets_ignores_the_minimum_tax_figures() -> None:
    rows = (("100", "10000", "0"), ("50", "5000", "0"))

    assert totals(capability().compute(given(*rows, line_7="400", line_8="50", line_11="80"))) == (
        totals(capability().compute(given(*rows)))
    )
    assert capability().compute(given(*rows, line_7="400", line_8="50", line_11="80")).trace == (
        capability().compute(given(*rows)).trace
    )


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, *datasets: ParameterDataset[Any]) -> None:
        self._datasets = {(d.family, d.kind): d for d in datasets}

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if tax_year != 2025 or (family, kind) not in self._datasets:
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._datasets[(family, kind)])


def service(dataset: ParameterDataset[RoundingOnly] | None = None) -> TaxComputationService:
    dataset = dataset or rounding()
    limit = threshold()
    rate_dataset = rate()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca-on/provincial_foreign_tax_credit",
        params={
            "rounding": dataset.family,
            "threshold": limit.family,
            "rate": rate_dataset.family,
        },
        consumes={
            "sheets": "ca/foreign_tax_credit_sheets",
            "net_income": "ex/net_income",
            "provincial_tax": "ex/provincial_tax",
            "minimum_tax_applies": "ex/minimum_tax_applies",
            "non_business_tax_paid": "ex/non_business_tax_two_thirds",
            "business_tax_paid": "ex/business_tax_paid",
            "special_foreign_tax_credit": "ex/special_foreign_tax_credit",
        },
        produces={"total": "ex/provincial_credit"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(
            frozenset(
                {
                    "ca/foreign_tax_credit_sheets",
                    "ex/net_income",
                    "ex/provincial_tax",
                    "ex/minimum_tax_applies",
                    "ex/non_business_tax_two_thirds",
                    "ex/business_tax_paid",
                    "ex/special_foreign_tax_credit",
                }
            )
        ),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/provincial_credit",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (SHEETS, NET_INCOME, PROVINCIAL_TAX, MINIMUM_TAX, LINE_7, LINE_8, LINE_11, CREDIT):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset, limit, rate_dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry_and_its_dataset() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, ProvincialForeignTaxCredit)
    assert built.consumes == frozenset(
        {SHEETS, NET_INCOME, PROVINCIAL_TAX, MINIMUM_TAX, LINE_7, LINE_8, LINE_11}
    )
    assert built.produces == frozenset({CREDIT})


def test_a_computation_gives_the_total_of_line_5() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given(US, UK))["ca-on/return"][
        0
    ]

    assert worksheet.get(CREDIT).value == D("100")
    assert isinstance(worksheet.producer_of(CREDIT), ProvincialForeignTaxCredit)
    assert worksheet.trace == (
        sheet_line(1, "1500", "1400", "100", "10000", "500.00", "100"),
        sheet_line(2, "100", "100", "0", "5000", "250.00", "0"),
        ItemsTotalLine(CREDIT, ((1, D("100")), (2, D("0"))), D("100")),
    )


def test_a_computation_works_the_minimum_tax_line_2_once_on_the_totals() -> None:
    # Line 2 = 150 x 1.01 / 250 = 0.606, half-up 0.61, so line 3 is 149.39 (per sheet it would be
    # 149.40); line 4 = 15000 x 5000 / 100000 = 750.00, so line 5 is 149.39.
    worksheet = service().compute(
        JurisdictionCode("CA-ON"),
        2025,
        *given(
            ("100", "10000", "0"),
            ("50", "5000", "0"),
            minimum_tax=1,
            line_8="100",
            line_11="1.01",
        ),
    )["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("149.39")


def test_a_computation_with_no_sheets_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given())["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("0")


def test_a_computation_applies_the_datasets_rounding() -> None:
    whole = RoundTo(D("1"), RoundingMode.FLOOR)

    worksheet = service(rounding(whole)).compute(
        JurisdictionCode("CA-ON"),
        2025,
        *given(("50", "10", "0"), net_income="300", provincial_tax="100"),
    )["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("3")


def test_a_line_2_above_line_1_is_refused_with_a_message() -> None:
    # One sheet of 100 with line 11 of 150 over a divisor of 100: line 2 = 150, more than line 1.
    with pytest.raises(ValidationError, match="more than the 100"):
        minimum_tax_total(("100", "10000", "0"), line_7="0", line_8="0", line_11="150")


def test_a_line_2_a_cent_above_line_1_from_line_7_in_cents_is_line_1() -> None:
    # Line 7 is 2500.24 x 0.666666 = 1666.8... in cents, 1666.82 (as T691 prints it); the divisor
    # 1666.82 / 0.666666 = 2500.2475... is under the tax paid plus a cent, so with a full federal
    # credit (line 11 = 2500.24) line 2 = 2500.24 x 2500.24 / 2500.2475... rounds to 2500.25.
    # Line 2 is held at line 1, 2500.24, so line 3 is 0 and so is the credit.
    assert minimum_tax_total(
        ("2500.24", "20000", "0"), line_7="1666.82", line_8="0", line_11="2500.24"
    ) == D("0.00")
