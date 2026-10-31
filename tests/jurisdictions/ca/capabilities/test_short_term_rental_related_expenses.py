"""Unit tests for ShortTermRentalRelatedExpenses, the Chart A total of Form T776 line 9365.

Form T776, Chart A "Enter each short-term rental or mixed rental property on a separate row", with
the columns "Related portion of the total from line 9365 of Part 4" (column 3), "Number of days the
residential property was a non compliant short-term rental" (column 4) and "Number of days the
residential property was a short-term rental" (column 5). Form T776 Part 4 line 9365 is the total
"Short-term rental portion of total expenses", and column 3 of the rows, added, must not be above
it.

The capability consumes the record list of those rows and produces the total of its one column: it
adds column 3 of every row exactly, with no rounding (it has no dataset), is 0 for no rows, and
records one `RecordTotalLine` naming each row's amount by position from 1. It mirrors
`ShortTermRentalGrossRents`. Its slots: no parameter slot, one consumed slot `units` (the record
list) and one produced slot `output`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.adapters.inbound.trace_english import EnglishTraceRenderer
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import InvalidCapabilityError, MissingArtifactError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import RecordTotalLine
from tax_engine.jurisdictions.ca.capabilities.short_term_rental_related_expenses import (
    ShortTermRentalRelatedExpenses,
)
from tax_engine.jurisdictions.ca.catalog import (
    SHORT_TERM_RENTAL_DAYS,
    SHORT_TERM_RENTAL_NON_COMPLIANT_DAYS,
    SHORT_TERM_RENTAL_RELATED_EXPENSES,
    SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL,
    SHORT_TERM_RENTAL_UNITS,
)
from tests.manifest_support import required_inputs

D = Decimal

# A row is (column 3 "Related portion of the total from line 9365", column 4 non-compliant days,
# column 5 short-term days), as Chart A's columns are entered.
Row = tuple[str, int, int]


def capability() -> ShortTermRentalRelatedExpenses:
    return ShortTermRentalRelatedExpenses(
        units=SHORT_TERM_RENTAL_UNITS, output=SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL
    )


def units(*rows: Row) -> Artifact[Any]:
    """A `ca/short_term_rental_units` artifact of one record per row, in order."""
    records: list[Mapping[ArtifactKind[Any], object]] = [
        {
            SHORT_TERM_RENTAL_RELATED_EXPENSES: D(related),
            SHORT_TERM_RENTAL_NON_COMPLIANT_DAYS: non_compliant,
            SHORT_TERM_RENTAL_DAYS: days,
        }
        for related, non_compliant, days in rows
    ]
    return Artifact(SHORT_TERM_RENTAL_UNITS, RecordList(SHORT_TERM_RENTAL_UNITS.fields, records))


def total_of(*rows: Row) -> Decimal:
    (artifact,) = capability().compute((units(*rows),)).outputs
    assert artifact.kind == SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL
    assert isinstance(artifact.value, Decimal)
    return artifact.value


def column(*amounts: str) -> list[Row]:
    """Rows whose column 3 is each amount in order, with 30 of 84 non-compliant days."""
    return [(amount, 30, 84) for amount in amounts]


def test_is_registered_as_ca_short_term_rental_related_expenses() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/short_term_rental_related_expenses")
        is ShortTermRentalRelatedExpenses
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "short_term_rental_related_expenses" in ca_capabilities.__all__
    assert (
        ca_capabilities.short_term_rental_related_expenses.ShortTermRentalRelatedExpenses
        is ShortTermRentalRelatedExpenses
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({SHORT_TERM_RENTAL_UNITS})
    assert capability().produces == frozenset({SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ShortTermRentalRelatedExpenses)
    assert "produces" not in vars(ShortTermRentalRelatedExpenses)


def test_declares_its_slots() -> None:
    assert ShortTermRentalRelatedExpenses.PARAMETERS == {}
    assert ShortTermRentalRelatedExpenses.CONSUMES == {"units": RecordList}
    assert ShortTermRentalRelatedExpenses.PRODUCES == {"output": Decimal}
    assert not ShortTermRentalRelatedExpenses.is_list_slot("units")


def test_its_slots_are_read_only() -> None:
    for slots in (
        ShortTermRentalRelatedExpenses.PARAMETERS,
        ShortTermRentalRelatedExpenses.CONSUMES,
        ShortTermRentalRelatedExpenses.PRODUCES,
    ):
        assert isinstance(slots, MappingProxyType)
        assert isinstance(slots, Mapping)


def test_takes_no_parameter_dataset() -> None:
    with pytest.raises(TypeError):
        ShortTermRentalRelatedExpenses(  # type: ignore[call-arg]
            SHORT_TERM_RENTAL_UNITS, SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL, object()
        )


def test_rejects_a_money_kind_for_its_units() -> None:
    other = ArtifactKind("ex/not_a_list", Decimal)

    with pytest.raises(InvalidCapabilityError, match="ShortTermRentalRelatedExpenses.*'units'"):
        ShortTermRentalRelatedExpenses(units=other, output=SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL)  # type: ignore[arg-type]


def test_rejects_a_record_list_kind_for_its_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="ShortTermRentalRelatedExpenses.*'output'"):
        ShortTermRentalRelatedExpenses(
            units=SHORT_TERM_RENTAL_UNITS,
            output=SHORT_TERM_RENTAL_UNITS,  # type: ignore[arg-type]
        )


# --- computing --------------------------------------------------------------------------------


def test_no_units_total_zero() -> None:
    assert total_of() == D("0")


def test_one_unit_is_its_own_total() -> None:
    assert total_of(*column("4300")) == D("4300")


def test_three_chart_a_rows_add_up_to_the_guide_total() -> None:
    # Guide T4036's example (Return EB): 2100, 1500 and 700 make 4300, line 9365.
    assert total_of(*column("2100", "1500", "700")) == D("4300")


def test_a_unit_with_no_related_portion_adds_nothing() -> None:
    assert total_of(*column("0", "6000")) == D("6000")


def test_equal_units_are_each_counted() -> None:
    assert total_of(*column("6000", "6000")) == D("12000")


def test_the_total_is_exact_and_never_rounded_to_the_cent() -> None:
    # A sum has no dataset, so no rounding: 0.001 + 0.002 = 0.003.
    assert total_of(*column("0.001", "0.002")) == D("0.003")
    assert str(total_of(*column("1000.005", "0.001"))) == "1000.006"


def test_the_total_is_exact_beyond_a_binary_float() -> None:
    assert total_of(*column("0.1", "0.2")) == D("0.3")


def test_the_total_does_not_depend_on_the_order_of_the_units() -> None:
    assert total_of(*column("1500", "2100")) == total_of(*column("2100", "1500"))


def test_reads_only_its_own_column() -> None:
    # The non-compliant days and the short-term days are not added.
    assert total_of(("100", 9999, 9999)) == D("100")


def test_the_days_are_not_added() -> None:
    assert total_of(("10", 2, 84), ("20", 3, 35)) == D("30")


# --- trace ------------------------------------------------------------------------------------


def test_produces_one_artifact_of_the_output_kind() -> None:
    result = capability().compute((units(*column("2100", "1500")),))

    assert result.outputs == (Artifact(SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL, D("3600")),)


def test_records_one_trace_line_naming_each_amount_in_order() -> None:
    result = capability().compute((units(*column("2100", "1500")),))

    assert result.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL,
            SHORT_TERM_RENTAL_RELATED_EXPENSES,
            (D("2100"), D("1500")),
            D("3600"),
        ),
    )


def test_records_one_trace_line_for_no_units() -> None:
    result = capability().compute((units(),))

    assert result.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL,
            SHORT_TERM_RENTAL_RELATED_EXPENSES,
            (),
            D("0"),
        ),
    )


def test_records_one_trace_line_whatever_the_number_of_units() -> None:
    for amounts in ((), ("1",), ("1", "2"), ("1", "2", "3", "4")):
        assert len(capability().compute((units(*column(*amounts)),)).trace) == 1


def test_the_trace_keeps_the_callers_order_not_the_sorted_one() -> None:
    (line,) = capability().compute((units(*column("6000", "24000")),)).trace

    assert isinstance(line, RecordTotalLine)
    assert line.amounts == (D("6000"), D("24000"))


def test_its_trace_reads_item_by_item_in_english() -> None:
    result = capability().compute((units(*column("2100", "1500")),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "short_term_rental_related_expenses_total: item 1 short_term_rental_related_expenses 2100 "
        "+ item 2 short_term_rental_related_expenses 1500 = 3600",
    )


def test_its_trace_for_no_units_says_no_items() -> None:
    result = capability().compute((units(),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "short_term_rental_related_expenses_total: no items = 0",
    )


def test_needs_its_units() -> None:
    with pytest.raises(MissingArtifactError, match="ShortTermRentalRelatedExpenses"):
        capability().compute(())


def test_does_not_consume_anything_else() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("1"))

    result = capability().compute((other, units(*column("2100"))))

    assert result.outputs == (Artifact(SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL, D("2100")),)


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (units(*column("2100", "1500")),)

    assert wired.compute(given) == wired.compute(given)


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _NoParameters:
    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service() -> TaxComputationService:
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/short_term_rental_related_expenses",
        params={},
        consumes={"units": "ca/short_term_rental_units"},
        produces={"output": "ca/short_term_rental_related_expenses_total"},
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
                exports=("ca/short_term_rental_related_expenses_total",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (SHORT_TERM_RENTAL_UNITS, SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _NoParameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, ShortTermRentalRelatedExpenses)
    assert built.consumes == frozenset({SHORT_TERM_RENTAL_UNITS})
    assert built.produces == frozenset({SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL})


def test_a_computation_gives_the_total() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, units(*column("2100", "1500", "700"))
    )["ca-on/return"][0]

    assert worksheet.get(SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL).value == D("4300")
    assert isinstance(
        worksheet.producer_of(SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL),
        ShortTermRentalRelatedExpenses,
    )
    assert worksheet.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL,
            SHORT_TERM_RENTAL_RELATED_EXPENSES,
            (D("2100"), D("1500"), D("700")),
            D("4300"),
        ),
    )


def test_a_computation_with_no_units_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, units())["ca-on/return"][0]

    assert worksheet.get(SHORT_TERM_RENTAL_RELATED_EXPENSES_TOTAL).value == D("0")
