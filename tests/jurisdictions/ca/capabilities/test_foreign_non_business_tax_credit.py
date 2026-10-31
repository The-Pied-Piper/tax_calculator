"""Unit tests for ForeignNonBusinessTaxCredit, lines 1 to 3 of Form T2209 (T1 line 40500).

Form T2209, federal non-business foreign tax credit: line 1 "Non-business income tax paid to a
foreign country (1) 43100"; line 2 "Net foreign non-business income (2) 43300 x Basic federal tax
(4) = 2 over Net income (3)"; line 3 "Enter whichever is less: the amount from line 1 or line 2".
Note (2): "If your net foreign non-business income is more than your net income, use your net income
in the calculation." "If you paid tax to more than one foreign country, and the total foreign
taxes paid to all foreign countries was more than $200, do the applicable calculation shown on
this form ... to each country on a separate sheet in Canadian dollars. Enter the total amount on
this form."

Its slots: two parameter slots, `rounding` (a `rounding_only` dataset: the rule for line 2) and
`pooling_threshold` (an `amount` dataset: the printed $200); three consumed slots, `countries` (a
record list whose records hold each country's line 1 and line 2 income), `net_income` and
`basic_federal_tax` (Decimal); two produced slots, `total` (Decimal), the sum of line 3, and
`sheets` (a record list of `ca/foreign_tax_credit_sheets`), one record per T2209 sheet: line 1 (tax
paid), the income used
on line 2 (after the cap at net income) and line 3. The sheets are one per country when worked
one by one, one pooled record otherwise (also for a single country), and none without
countries.

Per country (more than one country and total tax paid above the threshold): income is capped at
net income, line 2 is income x basic federal tax / net income through `ApplyRatio.ratio_of` (the
same object as `core/apply_ratio`), line 3 is the lesser of line 1 and line 2, and the total is the
sum of the countries' line 3. Otherwise one pooled calculation on the totals (tax paid summed,
income summed then capped at net income). No countries give 0, and net income is not consulted.
A net income of zero or less with at least one country gives line 2 of 0 without a division, so
line 3 and the total are 0, and each sheet's income is 0 (the cap is floored at 0). It records one
`ForeignTaxCreditLine` per country, by position from 1, then an `ItemsTotalLine`; the pooled case
records one `PooledForeignTaxCreditLine` alone.

The ticket's example: one country (10,000 of income, 1,500 of tax), net income 100,000, basic
federal tax 14,000 gives lesser(1,500, 1,400) = 1,400; a second country (5,000, 100) adds
lesser(100, 700) = 100, so 1,500 (total tax 1,600 is over 200), not the pooled lesser(1,600,
2,100) = 1,600. The kinds and dataset families are made up.
"""

from __future__ import annotations

import decimal
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capabilities.apply_ratio import ApplyRatio
from tax_engine.domain.capability import CapabilityRegistry, CapabilityResult
from tax_engine.domain.errors import (
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
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
from tax_engine.jurisdictions.ca.capabilities.foreign_non_business_tax_credit import (
    ForeignNonBusinessTaxCredit,
)
from tax_engine.jurisdictions.ca.catalog import (
    FOREIGN_BUSINESS_TAX_PAID,
    FOREIGN_BUSINESS_UNUSED_TAX_CREDITS,
    FOREIGN_NON_BUSINESS_TAX_PAID,
    FOREIGN_PROPERTY_TAX_PAID,
    FOREIGN_SURTAX_OUTSIDE_CANADA,
    FOREIGN_TAX_COUNTRIES,
    FOREIGN_TAX_CREDIT_SHEET_LINE_3,
    FOREIGN_TAX_CREDIT_SHEETS,
    NET_FOREIGN_BUSINESS_INCOME,
    NET_FOREIGN_NON_BUSINESS_INCOME,
    NET_FOREIGN_PROPERTY_INCOME,
)
from tax_engine.jurisdictions.ca.trace import ForeignTaxCreditLine, PooledForeignTaxCreditLine
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)

# The return-wide figures and the output come with the wiring; the tests use made-up kinds.
# Signed: T2209 note (3) takes line 23600, which can be negative (a net loss).
NET_INCOME = ArtifactKind("ex/net_income", Decimal)
BASIC_TAX = ArtifactKind("ex/basic_federal_tax", Decimal, non_negative=True)
CREDIT = ArtifactKind("ex/foreign_credit", Decimal, non_negative=True)
SHEETS = FOREIGN_TAX_CREDIT_SHEETS

# A country is (line 1 tax paid, net foreign non-business income), or those two followed by its
# four business figures: (business tax paid, unused business credits, net foreign business
# income, line 6 surtax), and then the foreign tax paid on income from property and that income.
# The two-figure form has zeros for the business and property figures.
Country = tuple[str, ...]

US: Country = ("1500", "10000")
UK: Country = ("100", "5000")


def rounding(rule: RoundingRule = CENT) -> ParameterDataset[RoundingOnly]:
    """By default half up to the cent."""
    return ParameterDataset(
        "ex/foreign_credit_rounding",
        2025,
        ROUNDING_ONLY,
        RoundingOnly(),
        rule,
        ("https://example.org/rounding",),
    )


def threshold(value: str = "200") -> ParameterDataset[Amount]:
    """By default the printed $200."""
    return ParameterDataset(
        "ex/foreign_credit_threshold",
        2025,
        AMOUNT,
        Amount(D(value)),
        CENT,
        ("https://example.org/t2209",),
    )


def limit_rate(value: str = "0.15") -> ParameterDataset[Rate]:
    """By default the printed 15%, half up to the cent."""
    return ParameterDataset(
        "ex/foreign_property_limit",
        2025,
        RATE,
        Rate(D(value)),
        CENT,
        ("https://example.org/t2209",),
    )


def capability(
    dataset: ParameterDataset[RoundingOnly] | None = None,
    pooling: ParameterDataset[Amount] | None = None,
) -> ForeignNonBusinessTaxCredit:
    return ForeignNonBusinessTaxCredit(
        dataset or rounding(),
        pooling or threshold(),
        limit_rate(),
        FOREIGN_TAX_COUNTRIES,
        NET_INCOME,
        BASIC_TAX,
        CREDIT,
        SHEETS,
    )


def countries(*rows: Country) -> Artifact[Any]:
    """A `ca/foreign_tax_countries` artifact of one record per country, in order."""
    records = []
    for row in rows:
        (
            tax,
            income,
            business_tax,
            unused,
            business_income,
            surtax,
            property_tax,
            property_income,
        ) = (
            *row,
            *("0",) * 6,
        )[:8]
        records.append(
            {
                FOREIGN_NON_BUSINESS_TAX_PAID: D(tax),
                NET_FOREIGN_NON_BUSINESS_INCOME: D(income),
                FOREIGN_BUSINESS_TAX_PAID: D(business_tax),
                FOREIGN_BUSINESS_UNUSED_TAX_CREDITS: D(unused),
                NET_FOREIGN_BUSINESS_INCOME: D(business_income),
                FOREIGN_SURTAX_OUTSIDE_CANADA: D(surtax),
                FOREIGN_PROPERTY_TAX_PAID: D(property_tax),
                NET_FOREIGN_PROPERTY_INCOME: D(property_income),
            }
        )
    return Artifact(FOREIGN_TAX_COUNTRIES, RecordList(FOREIGN_TAX_COUNTRIES.fields, records))


def given(
    *rows: Country, net_income: str = "100000", basic_tax: str = "14000"
) -> tuple[Artifact[Any], ...]:
    return (
        countries(*rows),
        Artifact(NET_INCOME, D(net_income)),
        Artifact(BASIC_TAX, D(basic_tax)),
    )


def totals(result: CapabilityResult) -> Decimal:
    """The `total` output of a computation."""
    (output,) = [a for a in result.outputs if a.kind == CREDIT]
    assert isinstance(output.value, Decimal)
    return output.value


def sheet_rows(result: CapabilityResult) -> list[tuple[Decimal, Decimal, Decimal]]:
    """The `sheets` output as (line 1, income used on line 2, line 3) per record, in order."""
    (output,) = [a for a in result.outputs if a.kind == SHEETS]
    assert isinstance(output.value, RecordList)
    return [
        (
            Decimal(record[FOREIGN_NON_BUSINESS_TAX_PAID]),
            Decimal(record[NET_FOREIGN_NON_BUSINESS_INCOME]),
            Decimal(record[FOREIGN_TAX_CREDIT_SHEET_LINE_3]),
        )
        for record in output.value.records
    ]


def business_sheet_rows(
    *rows: Country, net_income: str = "100000", basic_tax: str = "14000"
) -> list[tuple[Decimal, Decimal, Decimal, Decimal]]:
    """The `sheets` output as (business tax paid, unused business credits, net foreign business
    income used, line 6 surtax) per record, in order."""
    result = capability().compute(given(*rows, net_income=net_income, basic_tax=basic_tax))
    (output,) = [a for a in result.outputs if a.kind == SHEETS]
    assert isinstance(output.value, RecordList)
    return [
        (
            Decimal(record[FOREIGN_BUSINESS_TAX_PAID]),
            Decimal(record[FOREIGN_BUSINESS_UNUSED_TAX_CREDITS]),
            Decimal(record[NET_FOREIGN_BUSINESS_INCOME]),
            Decimal(record[FOREIGN_SURTAX_OUTSIDE_CANADA]),
        )
        for record in output.value.records
    ]


def sheets(
    *rows: Country,
    net_income: str = "100000",
    basic_tax: str = "14000",
    dataset: ParameterDataset[RoundingOnly] | None = None,
    pooling: ParameterDataset[Amount] | None = None,
) -> list[tuple[Decimal, Decimal, Decimal]]:
    wired = capability(dataset, pooling)
    return sheet_rows(wired.compute(given(*rows, net_income=net_income, basic_tax=basic_tax)))


def total(
    *rows: Country,
    net_income: str = "100000",
    basic_tax: str = "14000",
    dataset: ParameterDataset[RoundingOnly] | None = None,
    pooling: ParameterDataset[Amount] | None = None,
) -> Decimal:
    wired = capability(dataset, pooling)
    return totals(wired.compute(given(*rows, net_income=net_income, basic_tax=basic_tax)))


# --- contract and wiring ------------------------------------------------------------------------


def test_is_registered_as_ca_foreign_non_business_tax_credit() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/foreign_non_business_tax_credit")
        is ForeignNonBusinessTaxCredit
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "foreign_non_business_tax_credit" in ca_capabilities.__all__
    assert (
        ca_capabilities.foreign_non_business_tax_credit.ForeignNonBusinessTaxCredit
        is ForeignNonBusinessTaxCredit
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({FOREIGN_TAX_COUNTRIES, NET_INCOME, BASIC_TAX})
    assert capability().produces == frozenset({CREDIT, SHEETS})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ForeignNonBusinessTaxCredit)
    assert "produces" not in vars(ForeignNonBusinessTaxCredit)


def test_declares_its_slots() -> None:
    assert ForeignNonBusinessTaxCredit.PARAMETERS == {
        "rounding": ROUNDING_ONLY,
        "pooling_threshold": AMOUNT,
        "limit_rate": RATE,
    }
    assert ForeignNonBusinessTaxCredit.CONSUMES == {
        "countries": RecordList,
        "net_income": Decimal,
        "basic_federal_tax": Decimal,
    }
    assert ForeignNonBusinessTaxCredit.PRODUCES == {"total": Decimal, "sheets": RecordList}
    assert not ForeignNonBusinessTaxCredit.is_list_slot("countries")
    assert not ForeignNonBusinessTaxCredit.is_list_slot("sheets")


def test_its_slots_are_read_only() -> None:
    slots = (
        ForeignNonBusinessTaxCredit.PARAMETERS,
        ForeignNonBusinessTaxCredit.CONSUMES,
        ForeignNonBusinessTaxCredit.PRODUCES,
    )
    for each in slots:
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(ForeignNonBusinessTaxCredit.CONSUMES, Mapping[str, type])
    assert_type(ForeignNonBusinessTaxCredit.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = ForeignNonBusinessTaxCredit(
        rounding=rounding(),
        pooling_threshold=threshold(),
        limit_rate=limit_rate(),
        countries=FOREIGN_TAX_COUNTRIES,
        net_income=NET_INCOME,
        basic_federal_tax=BASIC_TAX,
        total=CREDIT,
        sheets=SHEETS,
    )

    assert totals(wired.compute(given(US))) == D("1400")
    assert sheet_rows(wired.compute(given(US))) == [(D("1500"), D("10000"), D("1400"))]


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        ForeignNonBusinessTaxCredit(  # type: ignore[call-arg]
            rounding(),
            threshold(),
            limit_rate(),
            FOREIGN_TAX_COUNTRIES,
            NET_INCOME,
            BASIC_TAX,
            CREDIT,
            SHEETS,
            CENT,
        )


def test_rejects_a_money_kind_for_its_countries() -> None:
    with pytest.raises(InvalidCapabilityError, match="ForeignNonBusinessTaxCredit.*'countries'"):
        ForeignNonBusinessTaxCredit(
            rounding(),
            threshold(),
            limit_rate(),
            CREDIT,  # type: ignore[arg-type]
            NET_INCOME,
            BASIC_TAX,
            CREDIT,
            SHEETS,
        )


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        ForeignNonBusinessTaxCredit(
            rate,  # type: ignore[arg-type]
            threshold(),
            limit_rate(),
            FOREIGN_TAX_COUNTRIES,
            NET_INCOME,
            BASIC_TAX,
            CREDIT,
            SHEETS,
        )
        ForeignNonBusinessTaxCredit(
            rounding(),
            rounding(),  # type: ignore[arg-type]
            limit_rate(),
            FOREIGN_TAX_COUNTRIES,
            NET_INCOME,
            BASIC_TAX,
            CREDIT,
            SHEETS,
        )
        ForeignNonBusinessTaxCredit(
            rounding(),
            threshold(),
            rounding(),  # type: ignore[arg-type]
            FOREIGN_TAX_COUNTRIES,
            NET_INCOME,
            BASIC_TAX,
            CREDIT,
            SHEETS,
        )

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(ForeignNonBusinessTaxCredit, "__type_params__", ())
    assert not getattr(ForeignNonBusinessTaxCredit, "__parameters__", ())


# --- computing: the ticket's examples -----------------------------------------------------------


def test_one_country_gives_the_lesser_of_its_tax_and_its_share_of_basic_tax() -> None:
    # lesser(1,500, 10,000 x 14,000 / 100,000 = 1,400)
    assert total(US) == D("1400")


def test_two_countries_over_200_are_worked_one_by_one_not_pooled() -> None:
    # lesser(1,500, 1,400) + lesser(100, 700) = 1,500; pooled would be lesser(1,600, 2,100).
    assert total(US, UK) == D("1500")


def test_the_total_does_not_depend_on_the_order_of_the_countries() -> None:
    assert total(UK, US) == total(US, UK)


def test_a_country_whose_tax_is_below_its_line_2_gives_its_tax() -> None:
    assert total(("300", "10000")) == D("300")


def test_a_country_whose_line_2_is_below_its_tax_gives_line_2() -> None:
    assert total(("5000", "10000")) == D("1400")


def test_a_country_with_no_tax_adds_nothing() -> None:
    assert total(US, ("0", "5000")) == D("1400")


def test_a_country_with_no_income_adds_nothing() -> None:
    assert total(US, ("500", "0")) == D("1400")


def test_a_zero_basic_federal_tax_gives_zero() -> None:
    assert total(US, UK, basic_tax="0") == D("0")


def test_cents_in_the_tax_paid_are_kept() -> None:
    assert total(("1234.56", "100000")) == D("1234.56")


# --- computing: no countries ---------------------------------------------------------------------


def test_no_countries_give_zero() -> None:
    output = Artifact(CREDIT, totals(capability().compute(given())))

    assert output == Artifact(CREDIT, D("0"))
    assert type(output.value) is Decimal
    assert not output.value.is_signed()


def test_no_countries_do_not_consult_net_income() -> None:
    assert total(net_income="0") == D("0")


def test_no_countries_do_not_consult_a_negative_net_income() -> None:
    assert total(net_income="-1") == D("0")


# --- computing: the $200 rule --------------------------------------------------------------------

# Two countries: 120 of tax on 10,000 (line 2 is 1,400) and 80 of tax on 100 (line 2 is 14).
BIG: Country = ("120", "10000")
SMALL: Country = ("80", "100")


def test_two_countries_with_exactly_200_of_tax_are_pooled() -> None:
    # Pooled: lesser(200, 10,100 x 14,000 / 100,000 = 1,414) = 200. Per country: 120 + 14 = 134.
    assert total(BIG, SMALL) == D("200")


def test_two_countries_with_200_01_of_tax_are_worked_one_by_one() -> None:
    assert total(BIG, ("80.01", "100")) == D("134")


def test_two_countries_with_less_than_200_of_tax_are_pooled() -> None:
    assert total(("100", "10000"), ("50", "100")) == D("150")


def test_the_threshold_comes_from_the_dataset() -> None:
    # US and UK together pay 1,600 of tax.
    assert total(US, UK, pooling=threshold("1000")) == D("1500")
    assert total(US, UK, pooling=threshold("2000")) == D("1600")
    assert total(US, UK, pooling=threshold("1600")) == D("1600")
    assert total(US, UK, pooling=threshold("1599.99")) == D("1500")


def test_a_pooled_calculation_adds_up_the_income_and_the_tax_first() -> None:
    # Pooled: lesser(1.00, (1 + 1) x 1 / 3 = 0.67) = 0.67; per country 0.33 + 0.33 = 0.66.
    assert total(("0.50", "1"), ("0.50", "1"), net_income="3", basic_tax="1") == D("0.67")


def test_a_single_country_gives_the_same_figure_pooled_or_not() -> None:
    assert total(US) == D("1400")
    assert total(("150", "10000")) == D("150")
    assert total(US, pooling=threshold("5000")) == D("1400")


# --- computing: income above net income ---------------------------------------------------------


def test_a_single_countrys_income_above_net_income_is_capped_at_net_income() -> None:
    # Uncapped, line 2 would be 150,000 x 14,000 / 100,000 = 21,000 and the credit 20,000.
    assert total(("20000", "150000")) == D("14000")


def test_income_equal_to_net_income_is_not_capped() -> None:
    assert total(("20000", "100000")) == D("14000")


def test_each_countrys_income_is_capped_when_worked_one_by_one() -> None:
    # 14,000 (income capped to 100,000) + lesser(300, 700) = 14,300.
    assert total(("20000", "150000"), ("300", "5000")) == D("14300")


def test_pooled_income_is_capped_after_it_is_added_up() -> None:
    # Basic federal tax 100: pooled income 130,000 is capped to 100,000, line 2 is 100.
    assert total(("100", "70000"), ("50", "60000"), basic_tax="100") == D("100")


# --- computing: net income zero or less ---------------------------------------------------------

# A net income of zero or less gives line 2 of 0 (no division), so line 3 and the total are 0.
ZERO_OR_LESS_NET_INCOMES = pytest.mark.parametrize("net_income", ["0", "-1", "-13010"])


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_a_credit_of_zero(net_income: str) -> None:
    assert total(US, net_income=net_income) == D("0")


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_zero_when_worked_one_by_one(net_income: str) -> None:
    assert total(US, UK, net_income=net_income) == D("0")


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_zero_when_pooled(net_income: str) -> None:
    assert total(BIG, SMALL, net_income=net_income) == D("0")


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_each_sheet_zero_income_and_line_3(
    net_income: str,
) -> None:
    assert sheets(US, UK, net_income=net_income) == [
        (D("1500"), D("0"), D("0")),
        (D("100"), D("0"), D("0")),
    ]


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_gives_the_pooled_sheet_zero_income_and_line_3(
    net_income: str,
) -> None:
    assert sheets(BIG, SMALL, net_income=net_income) == [(D("200"), D("0"), D("0"))]


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_keeps_the_sheets_other_figures(net_income: str) -> None:
    uk = ("60", "5000", "1", "10", "3000", "20")

    assert sheets(US_BUSINESS, uk, net_income=net_income) == [
        (D("100"), D("0"), D("0")),
        (D("60"), D("0"), D("0")),
    ]
    assert business_sheet_rows(US_BUSINESS, uk, net_income=net_income) == [
        (D("40"), D("5"), D("0"), D("0")),
        (D("1"), D("10"), D("0"), D("20")),
    ]


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_keeps_the_pooled_sheets_other_figures(
    net_income: str,
) -> None:
    assert sheets(US_BUSINESS, UK_BUSINESS, net_income=net_income) == [(D("160"), D("0"), D("0"))]
    assert business_sheet_rows(US_BUSINESS, UK_BUSINESS, net_income=net_income) == [
        (D("40"), D("15"), D("0"), D("20"))
    ]


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_traces_zero_lines_one_by_one(net_income: str) -> None:
    trace = capability().compute(given(US, UK, net_income=net_income)).trace

    assert trace == (
        country_line(1, "1500", "0", "0", "0", net=net_income),
        country_line(2, "100", "0", "0", "0", net=net_income),
        ItemsTotalLine(CREDIT, ((1, D("0")), (2, D("0"))), D("0")),
    )


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_traces_one_zero_pooled_line(net_income: str) -> None:
    trace = capability().compute(given(BIG, SMALL, net_income=net_income)).trace

    assert trace == (pooled_line(2, "200", "0", "0", "0", net=net_income),)


@ZERO_OR_LESS_NET_INCOMES
def test_a_net_income_of_zero_or_less_traces_a_single_country_as_a_zero_pooled_line(
    net_income: str,
) -> None:
    trace = capability().compute(given(US, net_income=net_income)).trace

    assert trace == (pooled_line(1, "1500", "0", "0", "0", net=net_income),)


def test_a_zero_net_income_is_worked_on_a_wired_capability_without_changing_it() -> None:
    wired = capability()

    assert totals(wired.compute(given(US, net_income="0"))) == D("0")

    assert totals(wired.compute(given(US))) == D("1400")


@ZERO_OR_LESS_NET_INCOMES
def test_a_computation_gives_a_credit_of_zero_for_a_net_income_of_zero_or_less(
    net_income: str,
) -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, *given(US, UK, net_income=net_income)
    )["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("0")
    sheet_list = worksheet.get(SHEETS).value
    assert isinstance(sheet_list, RecordList)
    assert [
        (
            r[FOREIGN_NON_BUSINESS_TAX_PAID],
            r[NET_FOREIGN_NON_BUSINESS_INCOME],
            r[FOREIGN_TAX_CREDIT_SHEET_LINE_3],
        )
        for r in sheet_list.records
    ] == [(D("1500"), D("0"), D("0")), (D("100"), D("0"), D("0"))]


# --- computing: rounding -------------------------------------------------------------------------


def test_line_2_is_rounded_half_up_to_the_cent() -> None:
    # 10 x 1 / 3 = 3.333...; 20 x 1 / 3 = 6.666...
    assert total(("50", "10"), net_income="300", basic_tax="100") == D("3.33")
    assert total(("50", "20"), net_income="300", basic_tax="100") == D("6.67")


def test_a_tie_rounds_half_up_by_the_dataset_rule() -> None:
    # 0.015 x 1 / 3 is exactly 0.005: half up gives 0.01, half even 0.00. Dividing first would
    # give 0.00499... and round down.
    assert total(("5", "0.015"), net_income="3", basic_tax="1") == D("0.01")
    half_even = RoundTo(D("0.01"), RoundingMode.HALF_EVEN)
    assert total(("5", "0.015"), net_income="3", basic_tax="1", dataset=rounding(half_even)) == D(
        "0.00"
    )


def test_each_country_is_rounded_before_the_countries_are_summed() -> None:
    # Three countries of 100 income, x 100 / 300: 33.33 x 3 = 99.99, not the rounded exact 100.00.
    rows = (("300", "100"), ("300", "100"), ("300", "100"))

    assert total(*rows, net_income="300", basic_tax="100") == D("99.99")


def test_a_whole_dollar_rule_rounds_each_country_to_the_dollar() -> None:
    whole = RoundTo(D("1"), RoundingMode.FLOOR)

    # 10 / 3 = 3.33 floors to 3; 20 / 3 = 6.67 floors to 6.
    assert total(
        ("300", "10"), ("300", "20"), net_income="300", basic_tax="100", dataset=rounding(whole)
    ) == D("9")


def test_no_rounding_keeps_an_exact_finite_quotient() -> None:
    # 0.015 x 1 / 2 = 0.0075.
    assert total(("5", "0.015"), net_income="2", basic_tax="1", dataset=rounding(NO_ROUNDING)) == D(
        "0.0075"
    )


def test_no_rounding_refuses_a_quotient_with_no_finite_expansion() -> None:
    with pytest.raises(decimal.Inexact):
        total(("5", "10"), net_income="300", basic_tax="100", dataset=rounding(NO_ROUNDING))


def test_a_rounded_line_2_carries_the_increments_scale() -> None:
    assert str(total(("5000", "10000"))) == "1400.00"


# --- computing: the shared ratio object ---------------------------------------------------------


def test_line_2_is_worked_by_the_shared_ratio_method_of_apply_ratio(
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

    assert total(US, UK) == D("1500")
    # amount = the country's income, numerator = basic federal tax, denominator = net income.
    assert calls == [
        (D("10000"), D("14000"), D("100000"), CENT),
        (D("5000"), D("14000"), D("100000"), CENT),
    ]


def test_the_pooled_line_2_is_worked_by_the_shared_ratio_method_too(
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

    assert total(BIG, SMALL) == D("200")
    assert calls == [(D("10100"), D("14000"), D("100000"), CENT)]


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(CREDIT, D("9"))

    result = capability().compute((other, *given(US)))

    assert totals(result) == D("1400")


@pytest.mark.parametrize("missing", ["foreign_tax_countries", "net_income", "basic_federal_tax"])
def test_a_missing_input_is_a_missing_artifact(missing: str) -> None:
    inputs = [a for a in given(US) if not a.kind.identifier.endswith(missing)]

    with pytest.raises(MissingArtifactError, match=missing):
        capability().compute(tuple(inputs))


def test_has_two_outputs_the_total_and_the_sheets() -> None:
    result = capability().compute(given(US, UK))

    assert [a.kind for a in result.outputs] == [CREDIT, SHEETS]
    assert isinstance(result.outputs[1].value, RecordList)


# --- computing: the sheets ----------------------------------------------------------------------


def test_two_countries_over_200_have_one_sheet_each_in_order() -> None:
    # Line 1, the income used on line 2, line 3 (the ticket's US and UK example).
    assert sheets(US, UK) == [
        (D("1500"), D("10000"), D("1400")),
        (D("100"), D("5000"), D("100")),
    ]


def test_the_sheets_keep_the_callers_order() -> None:
    assert sheets(UK, US) == [
        (D("100"), D("5000"), D("100")),
        (D("1500"), D("10000"), D("1400")),
    ]


def test_the_sheets_line_3_adds_up_to_the_total_when_worked_one_by_one() -> None:
    result = capability().compute(given(US, UK, ("300", "10000")))

    assert sum((line_3 for _, _, line_3 in sheet_rows(result)), D("0")) == totals(result)


def test_two_countries_at_exactly_200_have_one_pooled_sheet() -> None:
    # Pooled: tax 200, income 10,100, line 2 = 1,414, line 3 = 200.
    assert sheets(BIG, SMALL) == [(D("200"), D("10100"), D("200"))]


def test_two_countries_over_200_by_a_cent_have_two_sheets() -> None:
    assert sheets(BIG, ("80.01", "100")) == [
        (D("120"), D("10000"), D("120")),
        (D("80.01"), D("100"), D("14")),
    ]


def test_a_single_country_has_one_pooled_sheet() -> None:
    assert sheets(US) == [(D("1500"), D("10000"), D("1400"))]


def test_a_single_countrys_sheet_with_less_tax_than_line_2_has_its_tax_as_line_3() -> None:
    assert sheets(("300", "10000")) == [(D("300"), D("10000"), D("300"))]


def test_the_pooling_threshold_decides_the_number_of_sheets() -> None:
    assert len(sheets(US, UK, pooling=threshold("1000"))) == 2
    assert sheets(US, UK, pooling=threshold("1600")) == [(D("1600"), D("15000"), D("1600"))]


def test_no_countries_have_no_sheets() -> None:
    assert sheets() == []
    assert sheets(net_income="0") == []


def test_a_sheet_counts_the_income_after_the_cap_at_net_income() -> None:
    # One country: 150,000 of income is capped to the 100,000 of net income.
    assert sheets(("20000", "150000")) == [(D("20000"), D("100000"), D("14000"))]


def test_each_sheet_is_capped_when_worked_one_by_one() -> None:
    assert sheets(("20000", "150000"), ("300", "5000")) == [
        (D("20000"), D("100000"), D("14000")),
        (D("300"), D("5000"), D("300")),
    ]


def test_a_pooled_sheet_caps_the_summed_income() -> None:
    assert sheets(("100", "70000"), ("50", "60000"), basic_tax="100") == [
        (D("150"), D("100000"), D("100"))
    ]


def test_a_sheets_line_3_is_the_lesser_of_line_1_and_the_rounded_line_2() -> None:
    # 20 x 1 / 3 = 6.666... rounds to 6.67, below the 50 of tax.
    assert sheets(("50", "20"), net_income="300", basic_tax="100") == [
        (D("50"), D("20"), D("6.67"))
    ]


def test_sheets_are_rounded_country_by_country() -> None:
    rows = (("300", "100"), ("300", "100"), ("300", "100"))

    assert sheets(*rows, net_income="300", basic_tax="100") == [
        (D("300"), D("100"), D("33.33")),
        (D("300"), D("100"), D("33.33")),
        (D("300"), D("100"), D("33.33")),
    ]


def test_the_sheets_come_out_as_a_record_list_of_the_sheet_kind() -> None:
    result = capability().compute(given(US, UK))

    (artifact,) = [a for a in result.outputs if a.kind == SHEETS]
    assert isinstance(artifact.value, RecordList)
    assert artifact.value.fields == FOREIGN_TAX_CREDIT_SHEETS.fields


def test_the_sheets_of_no_countries_are_an_empty_record_list() -> None:
    (artifact,) = [a for a in capability().compute(given()).outputs if a.kind == SHEETS]

    assert isinstance(artifact.value, RecordList)
    assert artifact.value.records == ()


def test_the_sheets_do_not_change_the_trace() -> None:
    trace = capability().compute(given(US, UK)).trace

    assert len(trace) == 3
    assert isinstance(trace[-1], ItemsTotalLine)


# --- computing: the business figures on the sheets ---------------------------------------------

# T2209 note (5) business income tax paid for the year (first part of line 4), note (6) unused
# business foreign tax credits (second part of line 4), note (7) net foreign business income
# (line 43900, capped at net income) and line 6 (federal surtax on income allocated to "Other
# (Outside Canada)"). The credit total is the non-business line 3 only; the business lines are
# worked from the sheets by the capabilities of lines 4 to 11.
# Country with 100 non-business tax on 10,000 of income, and 40 of business tax, 5 unused, 6,000
# of business income and no surtax.
US_BUSINESS: Country = ("100", "10000", "40", "5", "6000", "0")
# Country with 60 on 5,000, and 0 of business tax, 10 unused, 3,000 of business income, 20 surtax.
UK_BUSINESS: Country = ("60", "5000", "0", "10", "3000", "20")


def test_the_business_figures_do_not_change_the_total() -> None:
    # Total foreign taxes 100 + 60 + 40 = 200: pooled, lesser(160, 15,000 x 14,000 / 100,000 =
    # 2,100) = 160, the non-business line 3 only.
    assert total(US_BUSINESS, UK_BUSINESS) == D("160")


def test_a_single_country_sheet_copies_its_business_figures() -> None:
    assert business_sheet_rows(US_BUSINESS) == [(D("40"), D("5"), D("6000"), D("0"))]
    assert sheets(US_BUSINESS) == [(D("100"), D("10000"), D("100"))]


def test_a_country_with_a_surtax_copies_it_on_its_sheet() -> None:
    assert business_sheet_rows(UK_BUSINESS) == [(D("0"), D("10"), D("3000"), D("20"))]


def test_pooled_countries_add_their_business_figures_on_the_one_sheet() -> None:
    # Total foreign taxes 100 + 60 + 40 + 0 = 200, not more than 200 (the unused credits of 5 and
    # 10 are not taxes paid for the year): one pooled sheet. Business tax 40 + 0, unused 5 + 10,
    # business income 6,000 + 3,000 = 9,000 (below net income 100,000), surtax 0 + 20.
    assert business_sheet_rows(US_BUSINESS, UK_BUSINESS) == [(D("40"), D("15"), D("9000"), D("20"))]
    assert sheets(US_BUSINESS, UK_BUSINESS) == [(D("160"), D("15000"), D("160"))]


def test_unused_business_credits_do_not_count_towards_the_200_of_foreign_taxes() -> None:
    # 100 + 60 of non-business tax and 40 of business tax is 200; 5 + 10 of unused credits would
    # make 215 if they were counted.
    assert len(sheets(US_BUSINESS, UK_BUSINESS)) == 1


def test_business_tax_paid_pushes_the_total_over_200_into_separate_sheets() -> None:
    # Non-business tax 100 + 60 = 160 alone is pooled. With 1 of business tax in the UK the total
    # foreign taxes are 100 + 60 + 40 + 1 = 201, more than 200: one sheet for each country.
    uk = ("60", "5000", "1", "10", "3000", "20")

    assert len(sheets(US_BUSINESS, UK_BUSINESS)) == 1
    assert sheets(US_BUSINESS, uk) == [
        (D("100"), D("10000"), D("100")),
        (D("60"), D("5000"), D("60")),
    ]
    assert business_sheet_rows(US_BUSINESS, uk) == [
        (D("40"), D("5"), D("6000"), D("0")),
        (D("1"), D("10"), D("3000"), D("20")),
    ]


def test_business_tax_alone_over_200_gives_separate_sheets() -> None:
    # No non-business tax at all: business tax paid 150 + 60 = 210 is more than 200.
    assert business_sheet_rows(
        ("0", "0", "150", "0", "1000", "0"), ("0", "0", "60", "0", "500", "0")
    ) == [
        (D("150"), D("0"), D("1000"), D("0")),
        (D("60"), D("0"), D("500"), D("0")),
    ]


def test_business_tax_paid_of_exactly_200_in_all_is_pooled() -> None:
    assert business_sheet_rows(
        ("0", "0", "150", "0", "1000", "0"), ("0", "0", "50", "0", "500", "0")
    ) == [(D("200"), D("0"), D("1500"), D("0"))]


def test_a_single_country_is_one_sheet_whatever_its_business_tax() -> None:
    assert business_sheet_rows(("0", "0", "5000", "0", "100", "0")) == [
        (D("5000"), D("0"), D("100"), D("0"))
    ]


def test_separate_sheets_cap_each_countrys_business_income_at_net_income() -> None:
    # 150 + 150 = 300 of non-business tax is over 200. Business income 120,000 is capped at the
    # net income 100,000 on its own sheet; 5,000 stays.
    assert business_sheet_rows(
        ("150", "0", "0", "0", "120000", "0"), ("150", "0", "0", "0", "5000", "0")
    ) == [
        (D("0"), D("0"), D("100000"), D("0")),
        (D("0"), D("0"), D("5000"), D("0")),
    ]


def test_a_pooled_sheet_caps_the_summed_business_income_at_net_income() -> None:
    # Total tax 20 is not over 200: pooled. 70,000 + 60,000 = 130,000 is capped at 100,000; each
    # country alone is below net income, so the cap comes after the sum (note 7).
    assert business_sheet_rows(
        ("10", "0", "0", "0", "70000", "0"), ("10", "0", "0", "0", "60000", "0")
    ) == [(D("0"), D("0"), D("100000"), D("0"))]


def test_a_single_countrys_business_income_above_net_income_is_capped() -> None:
    assert business_sheet_rows(("0", "0", "0", "0", "150000", "0")) == [
        (D("0"), D("0"), D("100000"), D("0"))
    ]


def test_the_business_figures_keep_the_callers_order() -> None:
    assert business_sheet_rows(
        ("150", "0", "10", "0", "1000", "0"), ("150", "0", "20", "0", "2000", "0")
    ) == [
        (D("10"), D("0"), D("1000"), D("0")),
        (D("20"), D("0"), D("2000"), D("0")),
    ]


def test_the_sheets_keep_the_business_record_fields_of_the_sheet_kind() -> None:
    (artifact,) = [a for a in capability().compute(given(US_BUSINESS)).outputs if a.kind == SHEETS]

    assert isinstance(artifact.value, RecordList)
    assert artifact.value.fields == FOREIGN_TAX_CREDIT_SHEETS.fields
    assert FOREIGN_BUSINESS_TAX_PAID in artifact.value.fields


def test_no_countries_have_no_business_sheets() -> None:
    assert business_sheet_rows() == []


# --- trace ---------------------------------------------------------------------------------------


def country_line(
    position: int,
    tax: str,
    income: str,
    line_2: str,
    result: str,
    rule: RoundingRule = CENT,
    net: str = "100000",
) -> Any:
    return ForeignTaxCreditLine(
        output=CREDIT,
        position=position,
        tax_paid=D(tax),
        income=D(income),
        net_income=D(net),
        basic_federal_tax=D("14000"),
        rounding=rule,
        line_2=D(line_2),
        result=D(result),
    )


def pooled_line(
    countries_count: int,
    tax: str,
    income: str,
    line_2: str,
    result: str,
    limit: str = "200",
    foreign_taxes: str | None = None,
    net: str = "100000",
) -> Any:
    return PooledForeignTaxCreditLine(
        output=CREDIT,
        countries=countries_count,
        tax_paid=D(tax),
        income=D(income),
        net_income=D(net),
        basic_federal_tax=D("14000"),
        total_foreign_taxes=D(foreign_taxes or tax),
        threshold=D(limit),
        rounding=CENT,
        line_2=D(line_2),
        result=D(result),
    )


def test_traces_one_line_per_country_then_the_total() -> None:
    trace = capability().compute(given(US, UK)).trace

    assert trace == (
        country_line(1, "1500", "10000", "1400.00", "1400.00"),
        country_line(2, "100", "5000", "700.00", "100"),
        ItemsTotalLine(CREDIT, ((1, D("1400.00")), (2, D("100"))), D("1500.00")),
    )


def test_traces_the_callers_order_with_positions_from_one() -> None:
    trace = capability().compute(given(UK, US)).trace

    assert trace == (
        country_line(1, "100", "5000", "700.00", "100"),
        country_line(2, "1500", "10000", "1400.00", "1400.00"),
        ItemsTotalLine(CREDIT, ((1, D("100")), (2, D("1400.00"))), D("1500.00")),
    )


def test_traces_the_income_after_the_cap_at_net_income() -> None:
    first, _, _ = capability().compute(given(("20000", "150000"), UK)).trace

    assert first == country_line(1, "20000", "100000", "14000.00", "14000.00")


def test_traces_the_pooled_calculation_as_one_line_alone() -> None:
    trace = capability().compute(given(BIG, SMALL)).trace

    assert trace == (pooled_line(2, "200", "10100", "1414.00", "200"),)


def test_traces_the_pooled_income_after_the_cap() -> None:
    trace = capability().compute(given(("100", "70000"), ("50", "60000"), basic_tax="100")).trace

    (line,) = trace
    assert isinstance(line, PooledForeignTaxCreditLine)
    assert line.income == D("100000")
    assert line.basic_federal_tax == D("100")
    assert line.line_2 == D("100.00")


def test_traces_a_single_country_as_a_pooled_line_of_one() -> None:
    trace = capability().compute(given(US)).trace

    assert trace == (pooled_line(1, "1500", "10000", "1400.00", "1400.00"),)


def test_traces_the_threshold_the_dataset_gave() -> None:
    (line,) = capability(pooling=threshold("2000")).compute(given(US, UK)).trace

    assert isinstance(line, PooledForeignTaxCreditLine)
    assert line.threshold == D("2000")
    assert line.countries == 2
    assert line.tax_paid == D("1600")


def test_traces_the_total_foreign_taxes_compared_with_the_threshold() -> None:
    # Non-business 100 + 60 plus business 40 + 0: the 200 compared with the threshold; the pooled
    # line's tax paid stays the non-business 160.
    (line,) = capability().compute(given(US_BUSINESS, UK_BUSINESS)).trace

    assert line == pooled_line(2, "160", "15000", "2100.00", "160", foreign_taxes="200")


def test_traces_the_total_foreign_taxes_of_a_single_country() -> None:
    (line,) = capability().compute(given(US_BUSINESS)).trace

    assert isinstance(line, PooledForeignTaxCreditLine)
    assert line.tax_paid == D("100")
    assert line.total_foreign_taxes == D("140")


def test_traces_separate_sheets_when_business_tax_pushes_the_total_over_200() -> None:
    uk = ("60", "5000", "1", "10", "3000", "20")

    first, second, total_line = capability().compute(given(US_BUSINESS, uk)).trace

    assert first == country_line(1, "100", "10000", "1400.00", "100")
    assert second == country_line(2, "60", "5000", "700.00", "60")
    assert isinstance(total_line, ItemsTotalLine)
    assert total_line.total == D("160")


def test_traces_no_countries_as_only_an_empty_total() -> None:
    assert capability().compute(given()).trace == (ItemsTotalLine(CREDIT, (), D("0")),)


def test_traces_the_rounding_rule_of_the_dataset() -> None:
    wired = capability(rounding(NO_ROUNDING))

    (line,) = wired.compute(given(("5", "0.015"), net_income="2", basic_tax="1")).trace

    assert isinstance(line, PooledForeignTaxCreditLine)
    assert line.rounding == NO_ROUNDING
    assert line.line_2 == D("0.0075")


def test_the_last_trace_line_amount_is_the_output() -> None:
    for rows in ((US, UK), (BIG, SMALL), (US,), ()):
        result = capability().compute(given(*rows))

        assert result.trace[-1].amount == totals(result)


def test_the_total_is_the_sum_of_its_items() -> None:
    *_, total_line = capability().compute(given(US, UK, ("300", "10000"))).trace

    assert isinstance(total_line, ItemsTotalLine)
    assert total_line.total == sum((amount for _, amount in total_line.items), D("0"))


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(given(US, UK)) == wired.compute(given(US, UK))


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


def service(
    dataset: ParameterDataset[RoundingOnly] | None = None,
) -> TaxComputationService:
    dataset = dataset or rounding()
    pooling = threshold()
    limit = limit_rate()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/foreign_non_business_tax_credit",
        params={
            "rounding": dataset.family,
            "pooling_threshold": pooling.family,
            "limit_rate": limit.family,
        },
        consumes={
            "countries": "ca/foreign_tax_countries",
            "net_income": "ex/net_income",
            "basic_federal_tax": "ex/basic_federal_tax",
        },
        produces={"total": "ex/foreign_credit", "sheets": "ca/foreign_tax_credit_sheets"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(
            frozenset({"ca/foreign_tax_countries", "ex/net_income", "ex/basic_federal_tax"})
        ),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/foreign_credit", "ca/foreign_tax_credit_sheets"),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (FOREIGN_TAX_COUNTRIES, NET_INCOME, BASIC_TAX, CREDIT, SHEETS):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset, pooling, limit),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry_and_its_datasets() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, ForeignNonBusinessTaxCredit)
    assert built.consumes == frozenset({FOREIGN_TAX_COUNTRIES, NET_INCOME, BASIC_TAX})
    assert built.produces == frozenset({CREDIT, SHEETS})


def test_a_computation_gives_the_per_country_total() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given(US, UK))["ca-on/return"][
        0
    ]

    assert worksheet.get(CREDIT).value == D("1500")
    assert isinstance(worksheet.producer_of(CREDIT), ForeignNonBusinessTaxCredit)
    assert worksheet.trace == (
        country_line(1, "1500", "10000", "1400.00", "1400.00"),
        country_line(2, "100", "5000", "700.00", "100"),
        ItemsTotalLine(CREDIT, ((1, D("1400.00")), (2, D("100"))), D("1500.00")),
    )


def test_a_computation_gives_the_sheets() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given(US, UK))["ca-on/return"][
        0
    ]

    sheet_list = worksheet.get(SHEETS).value
    assert isinstance(sheet_list, RecordList)
    assert [
        (r[FOREIGN_NON_BUSINESS_TAX_PAID], r[FOREIGN_TAX_CREDIT_SHEET_LINE_3])
        for r in sheet_list.records
    ] == [(D("1500"), D("1400")), (D("100"), D("100"))]
    assert isinstance(worksheet.producer_of(SHEETS), ForeignNonBusinessTaxCredit)


def test_a_computation_pools_two_countries_at_200_of_tax() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given(BIG, SMALL))[
        "ca-on/return"
    ][0]

    assert worksheet.get(CREDIT).value == D("200")


def test_a_computation_with_no_countries_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given())["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("0")


def test_a_computation_with_no_countries_does_not_consult_a_negative_net_income() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *given(net_income="-1"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(CREDIT).value == D("0")


def test_a_computation_applies_the_datasets_rounding() -> None:
    whole = RoundTo(D("1"), RoundingMode.FLOOR)

    worksheet = service(rounding(whole)).compute(
        JurisdictionCode("CA-ON"),
        2025,
        *given(("50", "10"), net_income="300", basic_tax="100"),
    )["ca-on/return"][0]

    assert worksheet.get(CREDIT).value == D("3")


# --- the 15% limit on income from property (T2209 page 1 note) ---------------------------------

# $20,000 of foreign dividends taxed at 30% ($6,000), all of it on income from property, on a
# return whose basic federal tax over net income is above 15%: the ticket's example.
DIVIDENDS: Country = ("6000", "20000", "0", "0", "0", "0", "6000", "20000")


def test_property_tax_over_15_percent_is_left_out_of_line_1() -> None:
    # Line 1 is 6,000 less the 3,000 over 15% of 20,000; line 2 is 20,000 x 76,605.97 / 316,990.00
    # = 4,833.34; the credit is the lesser, 3,000.00 and not 4,833.34.
    assert sheets(DIVIDENDS, net_income="316990", basic_tax="76605.97") == [
        (D("3000.00"), D("20000"), D("3000.00"))
    ]
    assert total(DIVIDENDS, net_income="316990", basic_tax="76605.97") == D("3000.00")


def test_property_tax_at_15_percent_is_all_credited() -> None:
    assert total(
        ("3000", "20000", "0", "0", "0", "0", "3000", "20000"),
        net_income="316990",
        basic_tax="76605.97",
    ) == D("3000.00")


def test_only_the_property_part_of_the_tax_is_limited() -> None:
    # 6,500 paid, 6,000 of it on 20,000 of property income: 3,000 is over 15%, line 1 is 3,500.
    country = ("6500", "25000", "0", "0", "0", "0", "6000", "20000")

    assert sheets(country, net_income="316990", basic_tax="76605.97")[0][0] == D("3500.00")


def test_the_limit_is_rounded_with_the_datasets_rule() -> None:
    # 15% of 1.10 is 0.165, 0.17 half up: the excess of 1.00 of tax is 0.83.
    country = ("1", "1.10", "0", "0", "0", "0", "1", "1.10")

    assert sheets(country, net_income="100000", basic_tax="14000")[0][0] == D("0.17")


def test_the_limit_applies_to_each_country_on_its_own() -> None:
    # One over (300 of tax on 1,000 is 150 over), one under: only the first is limited.
    over: Country = ("300", "1000", "0", "0", "0", "0", "300", "1000")
    under: Country = ("100", "1000", "0", "0", "0", "0", "100", "1000")

    assert [row[0] for row in sheets(over, under, net_income="100000", basic_tax="50000")] == [
        D("150.00"),
        D("100"),
    ]


def test_the_200_threshold_counts_the_tax_actually_paid() -> None:
    # 150 + 80 = 230 paid is over 200, so one sheet each, though the limited 15 + 80 is not.
    first: Country = ("150", "1000", "0", "0", "0", "0", "150", "100")
    second: Country = ("80", "1000")

    assert len(sheets(first, second)) == 2


def test_traces_the_line_1_used_after_the_limit() -> None:
    trace = capability().compute(given(DIVIDENDS, net_income="316990", basic_tax="76605.97")).trace

    (line,) = trace
    assert isinstance(line, PooledForeignTaxCreditLine)
    assert line.tax_paid == D("3000.00")
    assert line.line_2 == D("4833.34")
    assert line.result == D("3000.00")
