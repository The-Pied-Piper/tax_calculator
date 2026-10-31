"""Unit tests for ShortTermRentalNonCompliantCca, Chart B line C of Form T776.

Form T776, Chart B, "Non-compliant amount of CCA for short-term rentals": "Enter each short-term
rental or mixed rental property on a separate row"; "Column 1: Class number"; "Column 4: Related
portion of the available CCA from column 21 in Area A"; "Column 7 ***: Non-compliant amount
(column 4 multiplied by column 5 divided by column 6)"; "Line C: Total non-compliant amount of
CCA for short-term rentals: Total of column 7 (enter on line 9367 of Part 4)".

Its slots: one parameter slot, `rounding` (a `rounding_only` dataset: the rule for column 7), one
consumed slot `units` (a record list whose records hold each row's columns 1, 4, 5 and 6) and one
produced slot `output`. Each row is worked on its own: column 7 is column 4 times column 5 over
column 6 as an exact fraction, rounded once with the dataset's rule, and the output is the total of
the rounded rows, 0 for no rows, whatever the classes. A row whose column 6 is 0, or whose column 5
is above column 6, is a ValidationError naming the row. It records one
`ShortTermRentalNonCompliantCcaLine` per row, then an `ItemsTotalLine`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactRegistry
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
from tax_engine.jurisdictions.ca.capabilities.short_term_rental_non_compliant_cca import (
    ShortTermRentalNonCompliantCca,
)
from tax_engine.jurisdictions.ca.catalog import SHORT_TERM_RENTAL_CCA_UNITS
from tax_engine.jurisdictions.ca.trace import ShortTermRentalNonCompliantCcaLine
from tests.jurisdictions.ca.capabilities.short_term_rental_cca import (
    CENT,
    CLASS_8_ROW,
    LINE_9367,
    THIRD_ROW,
    TICKET_ROW,
    D,
    Row,
    rounding,
    units,
)
from tests.manifest_support import required_inputs


def capability(
    dataset: ParameterDataset[RoundingOnly] | None = None,
) -> ShortTermRentalNonCompliantCca:
    return ShortTermRentalNonCompliantCca(
        dataset or rounding(), SHORT_TERM_RENTAL_CCA_UNITS, LINE_9367
    )


def compute(wired: ShortTermRentalNonCompliantCca, *rows: Row) -> Artifact[Any]:
    (output,) = wired.compute((units(*rows),)).outputs
    return output


def total(*rows: Row, dataset: ParameterDataset[RoundingOnly] | None = None) -> Decimal:
    value = compute(capability(dataset), *rows).value
    assert isinstance(value, Decimal)
    return value


def test_is_registered_as_ca_short_term_rental_non_compliant_cca() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/short_term_rental_non_compliant_cca")
        is ShortTermRentalNonCompliantCca
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "short_term_rental_non_compliant_cca" in ca_capabilities.__all__
    assert (
        ca_capabilities.short_term_rental_non_compliant_cca.ShortTermRentalNonCompliantCca
        is ShortTermRentalNonCompliantCca
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({SHORT_TERM_RENTAL_CCA_UNITS})
    assert capability().produces == frozenset({LINE_9367})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ShortTermRentalNonCompliantCca)
    assert "produces" not in vars(ShortTermRentalNonCompliantCca)


def test_declares_its_slots() -> None:
    assert ShortTermRentalNonCompliantCca.PARAMETERS == {
        "rounding": ROUNDING_ONLY,
    }
    assert ShortTermRentalNonCompliantCca.CONSUMES == {"units": RecordList}
    assert ShortTermRentalNonCompliantCca.PRODUCES == {"output": Decimal}
    assert not ShortTermRentalNonCompliantCca.is_list_slot("units")


def test_its_slots_are_read_only() -> None:
    slots = (
        ShortTermRentalNonCompliantCca.PARAMETERS,
        ShortTermRentalNonCompliantCca.CONSUMES,
        ShortTermRentalNonCompliantCca.PRODUCES,
    )
    for each in slots:
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(ShortTermRentalNonCompliantCca.PARAMETERS, Mapping[str, ParameterKind[Any]])
    assert_type(ShortTermRentalNonCompliantCca.CONSUMES, Mapping[str, type])
    assert_type(ShortTermRentalNonCompliantCca.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = ShortTermRentalNonCompliantCca(
        rounding=rounding(),
        units=SHORT_TERM_RENTAL_CCA_UNITS,
        output=LINE_9367,
    )

    assert compute(wired, TICKET_ROW) == Artifact(LINE_9367, D("300.00"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        ShortTermRentalNonCompliantCca(  # type: ignore[call-arg]
            rounding(), SHORT_TERM_RENTAL_CCA_UNITS, LINE_9367, CENT
        )


def test_rejects_a_money_kind_for_its_units() -> None:
    with pytest.raises(InvalidCapabilityError, match="ShortTermRentalNonCompliantCca.*'units'"):
        ShortTermRentalNonCompliantCca(
            rounding(),
            LINE_9367,  # type: ignore[arg-type]
            LINE_9367,
        )


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        ShortTermRentalNonCompliantCca(
            rate,  # type: ignore[arg-type]
            SHORT_TERM_RENTAL_CCA_UNITS,
            LINE_9367,
        )

    assert callable(wire)


# --- computing ----------------------------------------------------------------------------------


def test_no_rows_give_zero() -> None:
    output = compute(capability())

    assert output == Artifact(LINE_9367, D("0"))
    assert type(output.value) is Decimal
    assert not output.value.is_signed()


def test_the_ticket_row_gives_300_on_line_9367() -> None:
    # 900 of related CCA, 30 non-compliant days of 90: 900 x 30 / 90.
    assert total(TICKET_ROW) == D("300.00")


def test_the_total_adds_the_rows_of_every_class() -> None:
    # Return AV: 300.00 and 33.33 in class 1, 250.00 in class 8.
    assert total(TICKET_ROW, THIRD_ROW, CLASS_8_ROW) == D("583.33")


def test_the_total_does_not_depend_on_the_order() -> None:
    assert total(CLASS_8_ROW, TICKET_ROW, THIRD_ROW) == total(TICKET_ROW, THIRD_ROW, CLASS_8_ROW)


def test_each_row_uses_its_own_days_never_pooled() -> None:
    # 100 x 10 / 20 = 50 and 100 x 0 / 50 = 0. Pooled: 200 x 10 / 70 = 28.57, which is wrong.
    assert total(("1", "100", 10, 20), ("1", "100", 0, 50)) == D("50.00")


def test_zero_non_compliant_days_give_plain_zero() -> None:
    value = total(("1", "900", 0, 90))

    assert value == D("0")
    assert not value.is_signed()


def test_the_whole_period_non_compliant_gives_column_4() -> None:
    assert total(("1", "1234.56", 365, 365)) == D("1234.56")


def test_the_quotient_is_not_rounded_before_it_is_multiplied() -> None:
    # 0.015 x 1 / 3 is exactly 0.005, a tie that half-up takes to 0.01.
    assert total(("1", "0.015", 1, 3)) == D("0.01")


def test_a_large_figure_is_exact() -> None:
    assert total(("1", "99999999.99", 7, 9)) == D("77777777.77")


def test_each_row_is_rounded_half_up_to_the_cent_before_the_rows_are_summed() -> None:
    assert total(("1", "100", 2, 3)) == D("66.67")
    assert total(THIRD_ROW, THIRD_ROW, THIRD_ROW) == D("99.99")
    assert total(("1", "0.01", 1, 2), ("1", "0.01", 1, 2)) == D("0.02")


def test_the_rounding_rule_comes_from_the_dataset() -> None:
    half_even = RoundTo(D("0.01"), RoundingMode.HALF_EVEN)

    assert total(("1", "0.01", 1, 2), dataset=rounding(half_even)) == D("0.00")
    assert total(("1", "0.01", 1, 2), dataset=rounding(CENT)) == D("0.01")


def test_no_rounding_keeps_the_exact_amount() -> None:
    assert total(("1", "0.015", 1, 2), dataset=rounding(NO_ROUNDING)) == D("0.0075")


def test_a_rounded_amount_carries_the_increments_scale() -> None:
    assert str(total(TICKET_ROW)) == "300.00"
    assert str(total(TICKET_ROW, CLASS_8_ROW)) == "550.00"


def test_the_class_number_does_not_change_the_amount() -> None:
    assert total(("10.1", "900", 30, 90)) == total(("1", "900", 30, 90))


# --- computing: refused rows --------------------------------------------------------------------


def test_a_row_whose_column_6_is_zero_is_refused_naming_the_row() -> None:
    with pytest.raises(ValidationError, match="row 1.*short_term_rental_days"):
        total(("1", "900", 0, 0))


def test_a_row_whose_column_5_is_above_column_6_is_refused_naming_the_row() -> None:
    with pytest.raises(ValidationError, match="row 2.*short_term_rental_non_compliant_days"):
        total(TICKET_ROW, ("1", "900", 91, 90))


def test_a_column_6_of_500_is_used_as_typed() -> None:
    # The form prints no maximum: 900 x 30 / 500 = 54.00 exactly.
    assert total(("1", "900", 30, 500)) == D("54.00")


def test_a_column_6_of_366_is_used_as_typed() -> None:
    # 3660 x 100 / 366 = 1000.00 exactly.
    assert total(("1", "3660", 100, 366)) == D("1000.00")


def test_a_column_6_of_500_with_500_non_compliant_days_is_used_as_typed() -> None:
    assert total(("1", "900", 500, 500)) == D("900.00")


def test_a_column_6_of_365_is_not_refused() -> None:
    # 900 x 30 / 365 = 73.9726..., half-up to 73.97.
    assert total(("1", "900", 30, 365)) == D("73.97")


def test_a_column_6_of_365_with_365_non_compliant_days_is_not_refused() -> None:
    assert total(("1", "900", 365, 365)) == D("900.00")


def test_a_second_row_of_500_days_is_used_as_typed() -> None:
    # 300.00 for the ticket row, 900 x 10 / 500 = 18.00 for the second.
    assert total(TICKET_ROW, ("1", "900", 10, 500)) == D("318.00")


def test_a_refusal_is_raised_when_computing_not_when_wiring() -> None:
    wired = capability()

    with pytest.raises(ValidationError):
        wired.compute((units(("1", "900", 91, 90)),))


def test_a_refused_row_leaves_no_partial_result() -> None:
    wired = capability()

    with pytest.raises(ValidationError):
        wired.compute((units(TICKET_ROW, ("1", "900", 91, 90)),))

    assert wired.compute((units(TICKET_ROW),)).outputs == (Artifact(LINE_9367, D("300.00")),)


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(LINE_9367, D("9"))

    result = capability().compute((other, units(TICKET_ROW)))

    assert result.outputs == (Artifact(LINE_9367, D("300.00")),)


def test_missing_units_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="short_term_rental_cca_units"):
        capability().compute(())


def test_has_one_output() -> None:
    assert len(capability().compute((units(TICKET_ROW, CLASS_8_ROW),)).outputs) == 1


# --- trace --------------------------------------------------------------------------------------


def row_line(
    position: int,
    class_number: str,
    related_cca: str,
    non_compliant_days: int,
    days: int,
    result: str,
    rule: RoundingRule = CENT,
) -> Any:
    return ShortTermRentalNonCompliantCcaLine(
        output=LINE_9367,
        position=position,
        class_number=D(class_number),
        related_cca=D(related_cca),
        non_compliant_days=non_compliant_days,
        days=days,
        rounding=rule,
        result=D(result),
    )


def test_traces_one_row_line_per_row_then_the_total() -> None:
    trace = capability().compute((units(TICKET_ROW, THIRD_ROW, CLASS_8_ROW),)).trace

    assert trace == (
        row_line(1, "1", "900", 30, 90, "300.00"),
        row_line(2, "1", "100", 1, 3, "33.33"),
        row_line(3, "8", "500", 45, 90, "250.00"),
        ItemsTotalLine(
            LINE_9367, ((1, D("300.00")), (2, D("33.33")), (3, D("250.00"))), D("583.33")
        ),
    )


def test_traces_no_rows_as_only_an_empty_total() -> None:
    assert capability().compute((units(),)).trace == (ItemsTotalLine(LINE_9367, (), D("0")),)


def test_traces_the_columns_as_given() -> None:
    row, _ = capability().compute((units(("10.1", "1234.56", 30, 90)),)).trace

    assert isinstance(row, ShortTermRentalNonCompliantCcaLine)
    assert row.class_number == D("10.1")
    assert row.related_cca == D("1234.56")
    assert row.non_compliant_days == 30
    assert type(row.non_compliant_days) is int
    assert row.days == 90
    assert type(row.days) is int
    assert row.result == D("411.52")


def test_traces_a_row_with_no_non_compliant_days_as_a_plain_zero() -> None:
    row, total_line = capability().compute((units(("1", "900", 0, 90)),)).trace

    assert isinstance(row, ShortTermRentalNonCompliantCcaLine)
    assert not row.result.is_signed()
    assert isinstance(total_line, ItemsTotalLine)
    assert not total_line.total.is_signed()


def test_traces_the_exact_amount_without_rounding() -> None:
    row, _ = capability(rounding(NO_ROUNDING)).compute((units(("1", "0.015", 1, 2)),)).trace

    assert isinstance(row, ShortTermRentalNonCompliantCcaLine)
    assert row.rounding == NO_ROUNDING
    assert row.result == D("0.0075")


def test_the_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute((units(TICKET_ROW, THIRD_ROW),))

    (output,) = result.outputs
    assert result.trace[-1].amount == output.value
    assert [line.amount for line in result.trace[:-1]] == [D("300.00"), D("33.33")]


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (units(TICKET_ROW, CLASS_8_ROW),)

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
        name="ca/short_term_rental_non_compliant_cca",
        params={"rounding": dataset.family},
        consumes={"units": "ca/short_term_rental_cca_units"},
        produces={"output": "ex/non_compliant_cca"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/short_term_rental_cca_units"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/non_compliant_cca",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (SHORT_TERM_RENTAL_CCA_UNITS, LINE_9367):
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
    assert isinstance(built, ShortTermRentalNonCompliantCca)
    assert built.consumes == frozenset({SHORT_TERM_RENTAL_CCA_UNITS})
    assert built.produces == frozenset({LINE_9367})


def test_a_computation_gives_the_total_of_column_7() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, units(TICKET_ROW, THIRD_ROW, CLASS_8_ROW)
    )["ca-on/return"][0]

    assert worksheet.get(LINE_9367).value == D("583.33")
    assert isinstance(worksheet.producer_of(LINE_9367), ShortTermRentalNonCompliantCca)


def test_a_computation_refuses_a_row_with_more_non_compliant_days_than_days() -> None:
    with pytest.raises(ValidationError, match="row 1"):
        service().compute(JurisdictionCode("CA-ON"), 2025, units(("1", "900", 91, 90)))


def test_a_computation_uses_a_row_with_more_days_than_a_year_as_typed() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, units(("1", "900", 30, 500)))[
        "ca-on/return"
    ][0]

    # 900 x 30 / 500 = 54.00
    assert worksheet.get(LINE_9367).value == D("54.00")
