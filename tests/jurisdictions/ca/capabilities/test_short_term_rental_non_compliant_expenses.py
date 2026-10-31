"""Unit tests for ShortTermRentalNonCompliantExpenses, Chart A line B of Form T776.

Form T776, Chart A, "Non-compliant amount of expenses for short-term rentals": "Enter each
short-term rental or mixed rental property on a separate row"; "Column 3: Related portion of the
total from line 9365 of Part 4"; "Column 4: Number of days the residential property was a non
compliant short-term rental"; "Column 5: Number of days the residential property was a short-term
rental"; "Column 6: Non-compliant amount (column 3 multiplied by column 4 divided by column 5)";
"Line B: Total non-compliant amount of expenses for short-term rentals: Total of column 6 (enter
on line 9366 of Part 4)".

Its slots: one parameter slot, `rounding` (a `rounding_only` dataset: the rule for column 6), one
consumed slot `units` (a record list whose records hold each row's columns 3, 4 and 5) and one
produced slot `output`. Each row is worked on its own: column 6 is column 3 times column 4 over
column 5 as an exact fraction, rounded once with the dataset's rule, and the output is the total of
the rounded rows, 0 for no rows. A row whose column 5 is 0, or whose column 4 is above column 5, is
a ValidationError naming the row. It records one `ShortTermRentalNonCompliantLine` per row, then an
`ItemsTotalLine`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
    ValidationError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
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
from tax_engine.jurisdictions.ca.capabilities.short_term_rental_non_compliant_expenses import (
    ShortTermRentalNonCompliantExpenses,
)
from tax_engine.jurisdictions.ca.catalog import (
    SHORT_TERM_RENTAL_DAYS,
    SHORT_TERM_RENTAL_NON_COMPLIANT_DAYS,
    SHORT_TERM_RENTAL_RELATED_EXPENSES,
    SHORT_TERM_RENTAL_UNITS,
)
from tax_engine.jurisdictions.ca.trace import ShortTermRentalNonCompliantLine
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)

# The output kind comes with the wiring; the tests use a made-up one.
NON_COMPLIANT = ArtifactKind("ex/non_compliant_expenses", Decimal, non_negative=True)

# A row is (column 3, column 4, column 5).
Row = tuple[str, int, int]


def rounding(rule: RoundingRule = CENT) -> ParameterDataset[RoundingOnly]:
    """By default half up to the cent."""
    return ParameterDataset(
        "ex/non_compliant_rounding",
        2025,
        ROUNDING_ONLY,
        RoundingOnly(),
        rule,
        ("https://example.org/rounding",),
    )


def capability(
    dataset: ParameterDataset[RoundingOnly] | None = None,
) -> ShortTermRentalNonCompliantExpenses:
    return ShortTermRentalNonCompliantExpenses(
        dataset or rounding(), SHORT_TERM_RENTAL_UNITS, NON_COMPLIANT
    )


def units(*rows: Row) -> Artifact[Any]:
    """A `ca/short_term_rental_units` artifact of one record per row, in order."""
    records: list[Mapping[ArtifactKind[Any], object]] = [
        {
            SHORT_TERM_RENTAL_RELATED_EXPENSES: D(expenses),
            SHORT_TERM_RENTAL_NON_COMPLIANT_DAYS: non_compliant,
            SHORT_TERM_RENTAL_DAYS: days,
        }
        for expenses, non_compliant, days in rows
    ]
    return Artifact(SHORT_TERM_RENTAL_UNITS, RecordList(SHORT_TERM_RENTAL_UNITS.fields, records))


def compute(wired: ShortTermRentalNonCompliantExpenses, *rows: Row) -> Artifact[Any]:
    (output,) = wired.compute((units(*rows),)).outputs
    return output


def total(*rows: Row, dataset: ParameterDataset[RoundingOnly] | None = None) -> Decimal:
    value = compute(capability(dataset), *rows).value
    assert isinstance(value, Decimal)
    return value


# The ticket's example: 900 of related expenses, 30 non-compliant days of 90.
TICKET_ROW: Row = ("900", 30, 90)
# 1,200 over 20 of 80 days is 300 too; 600 over 90 of 90 days is all 600.
QUARTER_ROW: Row = ("1200", 20, 80)
ALL_ROW: Row = ("600", 90, 90)


def test_is_registered_as_ca_short_term_rental_non_compliant_expenses() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/short_term_rental_non_compliant_expenses")
        is ShortTermRentalNonCompliantExpenses
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "short_term_rental_non_compliant_expenses" in ca_capabilities.__all__
    assert (
        ca_capabilities.short_term_rental_non_compliant_expenses.ShortTermRentalNonCompliantExpenses
        is ShortTermRentalNonCompliantExpenses
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({SHORT_TERM_RENTAL_UNITS})
    assert capability().produces == frozenset({NON_COMPLIANT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ShortTermRentalNonCompliantExpenses)
    assert "produces" not in vars(ShortTermRentalNonCompliantExpenses)


def test_declares_its_slots() -> None:
    assert ShortTermRentalNonCompliantExpenses.PARAMETERS == {
        "rounding": ROUNDING_ONLY,
    }
    assert ShortTermRentalNonCompliantExpenses.PARAMETERS["rounding"] is ROUNDING_ONLY
    assert ShortTermRentalNonCompliantExpenses.CONSUMES == {"units": RecordList}
    assert ShortTermRentalNonCompliantExpenses.PRODUCES == {"output": Decimal}
    assert not ShortTermRentalNonCompliantExpenses.is_list_slot("units")


def test_its_slots_are_read_only() -> None:
    slots = (
        ShortTermRentalNonCompliantExpenses.PARAMETERS,
        ShortTermRentalNonCompliantExpenses.CONSUMES,
        ShortTermRentalNonCompliantExpenses.PRODUCES,
    )
    for each in slots:
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(ShortTermRentalNonCompliantExpenses.PARAMETERS, Mapping[str, ParameterKind[Any]])
    assert_type(ShortTermRentalNonCompliantExpenses.CONSUMES, Mapping[str, type])
    assert_type(ShortTermRentalNonCompliantExpenses.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = ShortTermRentalNonCompliantExpenses(
        rounding=rounding(),
        units=SHORT_TERM_RENTAL_UNITS,
        output=NON_COMPLIANT,
    )

    assert compute(wired, TICKET_ROW) == Artifact(NON_COMPLIANT, D("300.00"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        ShortTermRentalNonCompliantExpenses(  # type: ignore[call-arg]
            rounding(), SHORT_TERM_RENTAL_UNITS, NON_COMPLIANT, CENT
        )


def test_rejects_a_money_kind_for_its_units() -> None:
    with pytest.raises(
        InvalidCapabilityError, match="ShortTermRentalNonCompliantExpenses.*'units'"
    ):
        ShortTermRentalNonCompliantExpenses(
            rounding(),
            NON_COMPLIANT,  # type: ignore[arg-type]
            NON_COMPLIANT,
        )


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        # A rate dataset is not a ParameterDataset[RoundingOnly]; the ignore fails under mypy
        # (warn_unused_ignores) if it is ever accepted.
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        ShortTermRentalNonCompliantExpenses(
            rate,  # type: ignore[arg-type]
            SHORT_TERM_RENTAL_UNITS,
            NON_COMPLIANT,
        )

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(ShortTermRentalNonCompliantExpenses, "__type_params__", ())
    assert not getattr(ShortTermRentalNonCompliantExpenses, "__parameters__", ())


# --- computing: how many rows -------------------------------------------------------------------


def test_no_rows_give_zero() -> None:
    output = compute(capability())

    assert output == Artifact(NON_COMPLIANT, D("0"))
    assert type(output.value) is Decimal
    assert not output.value.is_signed()


def test_one_row_gives_column_3_times_column_4_over_column_5() -> None:
    # The ticket's example: 900 x 30 / 90.
    assert total(TICKET_ROW) == D("300.00")


def test_two_rows_give_the_sum_of_their_own_amounts() -> None:
    # 300 and 1,200 x 20 / 80 = 300.
    assert total(TICKET_ROW, QUARTER_ROW) == D("600.00")


def test_three_rows_are_summed_one_by_one() -> None:
    assert total(TICKET_ROW, QUARTER_ROW, ALL_ROW) == D("1200.00")


def test_the_total_does_not_depend_on_the_order() -> None:
    assert total(ALL_ROW, TICKET_ROW, QUARTER_ROW) == total(TICKET_ROW, QUARTER_ROW, ALL_ROW)


def test_each_row_uses_its_own_days_never_pooled() -> None:
    # 100 x 10 / 20 = 50 and 100 x 0 / 50 = 0. Pooled: 200 x 10 / 70 = 28.57, which is wrong.
    assert total(("100", 10, 20), ("100", 0, 50)) == D("50.00")


def test_a_row_with_no_non_compliant_days_adds_nothing_to_the_others() -> None:
    assert total(("500", 0, 90), TICKET_ROW) == D("300.00")


def test_a_row_of_only_non_compliant_days_counts_all_of_its_expenses() -> None:
    assert total(ALL_ROW) == D("600.00")


# --- computing: the column 6 formula ------------------------------------------------------------


def test_zero_non_compliant_days_give_plain_zero() -> None:
    value = total(("900", 0, 90))

    assert value == D("0")
    assert not value.is_signed()


def test_zero_related_expenses_give_zero() -> None:
    assert total(("0", 30, 90)) == D("0")


def test_the_whole_period_non_compliant_gives_column_3() -> None:
    assert total(("1234.56", 365, 365)) == D("1234.56")


def test_one_day_of_a_long_period() -> None:
    # 1,000 x 1 / 3 = 333.33...
    assert total(("1000", 1, 3)) == D("333.33")


def test_column_4_multiplies_column_3_before_it_is_divided() -> None:
    assert total(("100", 2, 3)) == D("66.67")


def test_a_larger_period_gives_a_smaller_share() -> None:
    assert total(("900", 30, 180)) == D("150.00")


def test_cents_in_column_3_are_kept() -> None:
    # 1,234.56 x 30 / 90 = 411.52
    assert total(("1234.56", 30, 90)) == D("411.52")


def test_the_quotient_is_not_rounded_before_it_is_multiplied() -> None:
    # 0.015 x 1 / 3 is exactly 0.005, a tie that half-up takes to 0.01. Dividing first (1 / 3
    # = 0.333...) and multiplying after gives 0.00499999..., which rounds down to 0.00.
    assert total(("0.015", 1, 3)) == D("0.01")


def test_a_large_figure_is_exact() -> None:
    # 99,999,999.99 x 7 / 9 = 77,777,777.77 (exactly 77,777,777.7700000...).
    assert total(("99999999.99", 7, 9)) == D("77777777.77")


# --- computing: refused rows --------------------------------------------------------------------


def test_a_row_whose_column_5_is_zero_is_refused_naming_the_row() -> None:
    with pytest.raises(ValidationError, match="row 1.*short_term_rental_days"):
        total(("900", 0, 0))


def test_a_second_row_whose_column_5_is_zero_is_refused_naming_that_row() -> None:
    with pytest.raises(ValidationError, match="row 2.*short_term_rental_days"):
        total(TICKET_ROW, ("900", 0, 0))


def test_a_row_whose_column_4_is_above_column_5_is_refused_naming_the_row() -> None:
    with pytest.raises(ValidationError, match="row 1.*short_term_rental_non_compliant_days"):
        total(("900", 91, 90))


def test_a_third_row_whose_column_4_is_above_column_5_is_refused_naming_that_row() -> None:
    with pytest.raises(ValidationError, match="row 3.*short_term_rental_non_compliant_days"):
        total(TICKET_ROW, QUARTER_ROW, ("900", 10, 9))


def test_a_column_4_of_one_above_column_5_is_refused() -> None:
    with pytest.raises(ValidationError):
        total(("900", 2, 1))


def test_a_column_4_equal_to_column_5_is_not_refused() -> None:
    assert total(("900", 90, 90)) == D("900.00")


def test_a_column_4_one_below_column_5_is_not_refused() -> None:
    assert total(("900", 89, 90)) == D("890.00")


def test_a_column_5_of_500_is_used_as_typed() -> None:
    # The form prints no maximum: 900 x 30 / 500 = 54.00 exactly.
    assert total(("900", 30, 500)) == D("54.00")


def test_a_column_5_of_366_is_used_as_typed() -> None:
    # 3660 x 100 / 366 = 1000.00 exactly.
    assert total(("3660", 100, 366)) == D("1000.00")


def test_a_column_5_of_500_with_500_non_compliant_days_is_used_as_typed() -> None:
    assert total(("900", 500, 500)) == D("900.00")


def test_a_column_5_of_365_is_not_refused() -> None:
    # 900 x 30 / 365 = 73.9726..., half-up to 73.97.
    assert total(("900", 30, 365)) == D("73.97")


def test_a_column_5_of_365_with_365_non_compliant_days_is_not_refused() -> None:
    assert total(("900", 365, 365)) == D("900.00")


def test_a_second_row_of_500_days_is_used_as_typed() -> None:
    # 300.00 for the ticket row, 900 x 10 / 500 = 18.00 for the second.
    assert total(TICKET_ROW, ("900", 10, 500)) == D("318.00")


def test_a_refused_row_is_refused_though_the_others_are_fine() -> None:
    with pytest.raises(ValidationError, match="row 2"):
        total(TICKET_ROW, ("900", 91, 90), ALL_ROW)


def test_the_first_refused_row_is_the_one_named() -> None:
    with pytest.raises(ValidationError, match="row 2"):
        total(TICKET_ROW, ("900", 0, 0), ("900", 91, 90))


def test_a_refusal_is_raised_when_computing_not_when_wiring() -> None:
    wired = capability()

    with pytest.raises(ValidationError):
        wired.compute((units(("900", 91, 90)),))


# --- computing: rounding ------------------------------------------------------------------------


def test_each_row_is_rounded_half_up_to_the_cent() -> None:
    # 100 x 1 / 3 = 33.333...; 100 x 2 / 3 = 66.666...
    assert total(("100", 1, 3)) == D("33.33")
    assert total(("100", 2, 3)) == D("66.67")


def test_a_tie_rounds_half_up() -> None:
    # 0.01 x 1 / 2 = 0.005.
    assert total(("0.01", 1, 2)) == D("0.01")


def test_each_row_is_rounded_once_before_the_rows_are_summed() -> None:
    # Two rows of 0.005 each round to 0.01 each: 0.02, not the rounded exact sum 0.01.
    assert total(("0.01", 1, 2), ("0.01", 1, 2)) == D("0.02")


def test_the_sum_of_rounded_rows_can_differ_from_the_rounded_sum_of_exact_rows() -> None:
    # Three rows of 33.333... round to 33.33 each: 99.99, not the rounded exact sum 100.00.
    assert total(("100", 1, 3), ("100", 1, 3), ("100", 1, 3)) == D("99.99")


def test_the_rounding_rule_comes_from_the_dataset() -> None:
    half_even = RoundTo(D("0.01"), RoundingMode.HALF_EVEN)

    # 0.005 is a tie: half up gives 0.01, half even gives 0.00.
    assert total(("0.01", 1, 2), dataset=rounding(half_even)) == D("0.00")
    assert total(("0.01", 1, 2), dataset=rounding(CENT)) == D("0.01")


def test_a_whole_dollar_rule_rounds_each_row_to_the_dollar() -> None:
    whole = RoundTo(D("1"), RoundingMode.FLOOR)

    # 100 x 2 / 3 = 66.67 floors to 66, and 100 x 1 / 3 = 33.33 floors to 33.
    assert total(("100", 2, 3), ("100", 1, 3), dataset=rounding(whole)) == D("99")


def test_no_rounding_keeps_the_exact_amount() -> None:
    # 0.015 x 1 / 2 = 0.0075.
    assert total(("0.015", 1, 2), dataset=rounding(NO_ROUNDING)) == D("0.0075")


def test_a_rounded_amount_carries_the_increments_scale() -> None:
    assert str(total(TICKET_ROW)) == "300.00"
    assert str(total(TICKET_ROW, QUARTER_ROW)) == "600.00"


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(NON_COMPLIANT, D("9"))

    result = capability().compute((other, units(TICKET_ROW)))

    assert result.outputs == (Artifact(NON_COMPLIANT, D("300.00")),)


def test_missing_units_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="short_term_rental_units"):
        capability().compute(())


def test_has_one_output() -> None:
    assert len(capability().compute((units(TICKET_ROW, QUARTER_ROW),)).outputs) == 1


# --- trace --------------------------------------------------------------------------------------


def row_line(
    position: int,
    expenses: str,
    non_compliant_days: int,
    days: int,
    result: str,
    rule: RoundingRule = CENT,
) -> Any:
    return ShortTermRentalNonCompliantLine(
        output=NON_COMPLIANT,
        position=position,
        related_expenses=D(expenses),
        non_compliant_days=non_compliant_days,
        days=days,
        rounding=rule,
        result=D(result),
    )


def test_traces_one_row_line_per_row_then_the_total() -> None:
    trace = capability().compute((units(TICKET_ROW, QUARTER_ROW),)).trace

    assert trace == (
        row_line(1, "900", 30, 90, "300.00"),
        row_line(2, "1200", 20, 80, "300.00"),
        ItemsTotalLine(NON_COMPLIANT, ((1, D("300.00")), (2, D("300.00"))), D("600.00")),
    )


def test_traces_the_callers_order_with_positions_from_one() -> None:
    trace = capability().compute((units(ALL_ROW, TICKET_ROW, ("100", 2, 3)),)).trace

    assert trace == (
        row_line(1, "600", 90, 90, "600.00"),
        row_line(2, "900", 30, 90, "300.00"),
        row_line(3, "100", 2, 3, "66.67"),
        ItemsTotalLine(
            NON_COMPLIANT,
            ((1, D("600.00")), (2, D("300.00")), (3, D("66.67"))),
            D("966.67"),
        ),
    )


def test_traces_no_rows_as_only_an_empty_total() -> None:
    trace = capability().compute((units(),)).trace

    assert trace == (ItemsTotalLine(NON_COMPLIANT, (), D("0")),)


def test_traces_a_row_with_no_non_compliant_days_as_a_plain_zero() -> None:
    row, total_line = capability().compute((units(("900", 0, 90)),)).trace

    assert isinstance(row, ShortTermRentalNonCompliantLine)
    assert row.result == D("0")
    assert not row.result.is_signed()
    assert isinstance(total_line, ItemsTotalLine)
    assert not total_line.total.is_signed()


def test_traces_the_columns_as_given() -> None:
    row, _ = capability().compute((units(("1234.56", 30, 90)),)).trace

    assert isinstance(row, ShortTermRentalNonCompliantLine)
    assert row.related_expenses == D("1234.56")
    assert row.non_compliant_days == 30
    assert type(row.non_compliant_days) is int
    assert row.days == 90
    assert type(row.days) is int
    assert row.result == D("411.52")


def test_traces_the_datasets_rounding_rule_and_the_rounded_amounts() -> None:
    row, total_line = capability().compute((units(("100", 1, 3)),)).trace

    assert row == row_line(1, "100", 1, 3, "33.33")
    assert total_line == ItemsTotalLine(NON_COMPLIANT, ((1, D("33.33")),), D("33.33"))


def test_traces_the_exact_amount_without_rounding() -> None:
    wired = capability(rounding(NO_ROUNDING))

    row, _ = wired.compute((units(("0.015", 1, 2)),)).trace

    assert isinstance(row, ShortTermRentalNonCompliantLine)
    assert row.rounding == NO_ROUNDING
    assert row.result == D("0.0075")


def test_the_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute((units(TICKET_ROW, ("100", 2, 3)),))

    (output,) = result.outputs
    assert result.trace[-1].amount == output.value
    assert [line.amount for line in result.trace[:-1]] == [D("300.00"), D("66.67")]


def test_the_total_is_the_sum_of_its_items() -> None:
    *_, total_line = capability().compute((units(TICKET_ROW, ("100", 1, 3), ALL_ROW),)).trace

    assert isinstance(total_line, ItemsTotalLine)
    assert total_line.total == sum((amount for _, amount in total_line.items), D("0"))


def test_a_refused_row_leaves_no_partial_result() -> None:
    wired = capability()

    with pytest.raises(ValidationError):
        wired.compute((units(TICKET_ROW, ("900", 91, 90)),))

    assert wired.compute((units(TICKET_ROW),)).outputs == (Artifact(NON_COMPLIANT, D("300.00")),)


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (units(TICKET_ROW, QUARTER_ROW),)

    assert wired.compute(given) == wired.compute(given)


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, *datasets: ParameterDataset[Any]) -> None:
        self._datasets = datasets

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        for dataset in self._datasets:
            if (dataset.family, tax_year, dataset.kind) == (family, 2025, kind):
                return cast(ParameterDataset[T], dataset)
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service(
    dataset: ParameterDataset[RoundingOnly] | None = None,
) -> TaxComputationService:
    dataset = dataset or rounding()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/short_term_rental_non_compliant_expenses",
        params={"rounding": dataset.family},
        consumes={"units": "ca/short_term_rental_units"},
        produces={"output": "ex/non_compliant_expenses"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/short_term_rental_units"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/non_compliant_expenses",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (SHORT_TERM_RENTAL_UNITS, NON_COMPLIANT):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry_and_its_dataset() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, ShortTermRentalNonCompliantExpenses)
    assert built.consumes == frozenset({SHORT_TERM_RENTAL_UNITS})
    assert built.produces == frozenset({NON_COMPLIANT})


def test_a_computation_gives_the_per_row_total() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, units(TICKET_ROW, ("100", 2, 3))
    )["ca-on/return"][0]

    assert worksheet.get(NON_COMPLIANT).value == D("366.67")
    assert isinstance(worksheet.producer_of(NON_COMPLIANT), ShortTermRentalNonCompliantExpenses)
    assert worksheet.trace == (
        row_line(1, "900", 30, 90, "300.00"),
        row_line(2, "100", 2, 3, "66.67"),
        ItemsTotalLine(NON_COMPLIANT, ((1, D("300.00")), (2, D("66.67"))), D("366.67")),
    )


def test_a_computation_with_no_rows_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, units())["ca-on/return"][0]

    assert worksheet.get(NON_COMPLIANT).value == D("0")


def test_a_computation_refuses_a_row_with_more_non_compliant_days_than_days() -> None:
    with pytest.raises(ValidationError, match="row 1"):
        service().compute(JurisdictionCode("CA-ON"), 2025, units(("900", 91, 90)))


def test_a_computation_uses_a_row_with_more_days_than_a_year_as_typed() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, units(("900", 30, 500)))[
        "ca-on/return"
    ][0]

    # 900 x 30 / 500 = 54.00
    assert worksheet.get(NON_COMPLIANT).value == D("54.00")


def test_a_computation_applies_the_datasets_rounding() -> None:
    worksheet = service(rounding(RoundTo(D("1"), RoundingMode.FLOOR))).compute(
        JurisdictionCode("CA-ON"), 2025, units(("100", 2, 3))
    )["ca-on/return"][0]

    assert worksheet.get(NON_COMPLIANT).value == D("66")
