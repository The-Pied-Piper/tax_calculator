"""Unit tests for ShortTermRentalGrossRents, line 8140 of Form T776 Part 3.

Form T776, Part 3, "List the addresses of your rental properties." with the headings "Number
of units", "Gross rents for short-term rentals" and "Gross rents for all units" (one row for
each property), and "Line
8140: Total of your gross rents for short-term rentals in the year you receive them (add
amounts under "Gross rents for short-term rentals")".

The capability consumes the record list of those rows and produces the total of that one column:
it adds that field of every row exactly, with no rounding (it has no dataset), is 0 for no rows,
and records one `RecordTotalLine` naming each row's amount by position from 1. A row whose
"Gross rents for short-term rentals" is above its "Gross rents for all units" is refused
(`InputAboveBoundError`, naming the item and both fields); equal is valid. Its slots: no
parameter slot, one consumed slot `properties` (the record list) and one produced slot `output`.
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
from tax_engine.domain.errors import (
    InputAboveBoundError,
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import RecordTotalLine
from tax_engine.jurisdictions.ca.capabilities.short_term_rental_gross_rents import (
    ShortTermRentalGrossRents,
)
from tax_engine.jurisdictions.ca.catalog import (
    RENTAL_PROPERTIES,
    RENTAL_PROPERTY_GROSS_RENTS,
    RENTAL_PROPERTY_SHORT_TERM_RENTS,
    RENTAL_PROPERTY_UNITS,
    SHORT_TERM_RENTAL_GROSS_RENTS,
)
from tests.manifest_support import required_inputs

D = Decimal

# A row is (units, column "Gross rents for short-term rentals", column "Gross rents for all units").
Row = tuple[int, str, str]


def capability() -> ShortTermRentalGrossRents:
    return ShortTermRentalGrossRents(
        properties=RENTAL_PROPERTIES, output=SHORT_TERM_RENTAL_GROSS_RENTS
    )


def properties(*rows: Row) -> Artifact[Any]:
    """A `ca/rental_properties` artifact of one record per row, in order."""
    records: list[Mapping[ArtifactKind[Any], object]] = [
        {
            RENTAL_PROPERTY_UNITS: units,
            RENTAL_PROPERTY_SHORT_TERM_RENTS: D(short_term),
            RENTAL_PROPERTY_GROSS_RENTS: D(gross),
        }
        for units, short_term, gross in rows
    ]
    return Artifact(RENTAL_PROPERTIES, RecordList(RENTAL_PROPERTIES.fields, records))


def total_of(*rows: Row) -> Decimal:
    (artifact,) = capability().compute((properties(*rows),)).outputs
    assert artifact.kind == SHORT_TERM_RENTAL_GROSS_RENTS
    assert isinstance(artifact.value, Decimal)
    return artifact.value


def column(*amounts: str) -> list[Row]:
    """Rows whose own rent column is each amount in order, with gross rents above any of them."""
    return [(2, amount, "99999999") for amount in amounts]


def test_is_registered_as_ca_short_term_rental_gross_rents() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/short_term_rental_gross_rents")
        is ShortTermRentalGrossRents
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "short_term_rental_gross_rents" in ca_capabilities.__all__
    assert (
        ca_capabilities.short_term_rental_gross_rents.ShortTermRentalGrossRents
        is ShortTermRentalGrossRents
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({RENTAL_PROPERTIES})
    assert capability().produces == frozenset({SHORT_TERM_RENTAL_GROSS_RENTS})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ShortTermRentalGrossRents)
    assert "produces" not in vars(ShortTermRentalGrossRents)


def test_declares_its_slots() -> None:
    assert ShortTermRentalGrossRents.PARAMETERS == {}
    assert ShortTermRentalGrossRents.CONSUMES == {"properties": RecordList}
    assert ShortTermRentalGrossRents.PRODUCES == {"output": Decimal}
    assert not ShortTermRentalGrossRents.is_list_slot("properties")


def test_its_slots_are_read_only() -> None:
    for slots in (
        ShortTermRentalGrossRents.PARAMETERS,
        ShortTermRentalGrossRents.CONSUMES,
        ShortTermRentalGrossRents.PRODUCES,
    ):
        assert isinstance(slots, MappingProxyType)
        assert isinstance(slots, Mapping)


def test_takes_no_parameter_dataset() -> None:
    with pytest.raises(TypeError):
        ShortTermRentalGrossRents(  # type: ignore[call-arg]
            RENTAL_PROPERTIES, SHORT_TERM_RENTAL_GROSS_RENTS, object()
        )


def test_rejects_a_money_kind_for_its_properties() -> None:
    other = ArtifactKind("ex/not_a_list", Decimal)

    with pytest.raises(InvalidCapabilityError, match="ShortTermRentalGrossRents.*'properties'"):
        ShortTermRentalGrossRents(properties=other, output=SHORT_TERM_RENTAL_GROSS_RENTS)  # type: ignore[arg-type]


def test_rejects_a_record_list_kind_for_its_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="ShortTermRentalGrossRents.*'output'"):
        ShortTermRentalGrossRents(properties=RENTAL_PROPERTIES, output=RENTAL_PROPERTIES)  # type: ignore[arg-type]


# --- computing --------------------------------------------------------------------------------


def test_no_properties_total_zero() -> None:
    assert total_of() == D("0")


def test_one_property_is_its_own_total() -> None:
    assert total_of(*column("24000")) == D("24000")


def test_two_properties_add_up() -> None:
    assert total_of(*column("24000", "6000")) == D("30000")


def test_three_properties_add_up_with_cents() -> None:
    assert total_of(*column("24000", "6000", "1250.75")) == D("31250.75")


def test_a_property_with_no_rents_adds_nothing() -> None:
    assert total_of(*column("0", "6000")) == D("6000")


def test_equal_properties_are_each_counted() -> None:
    assert total_of(*column("6000", "6000")) == D("12000")


def test_the_total_is_exact_and_never_rounded_to_the_cent() -> None:
    # A sum has no dataset, so no rounding: 0.001 + 0.002 = 0.003.
    assert total_of(*column("0.001", "0.002")) == D("0.003")
    assert str(total_of(*column("1000.005", "0.001"))) == "1000.006"


def test_the_total_is_exact_beyond_a_binary_float() -> None:
    assert total_of(*column("0.1", "0.2")) == D("0.3")


def test_the_total_does_not_depend_on_the_order_of_the_properties() -> None:
    assert total_of(*column("6000", "24000")) == total_of(*column("24000", "6000"))


def test_reads_only_its_own_column() -> None:
    # The other rent column and the number of units are not added.
    assert total_of((5, "100", "9999")) == D("100")


def test_the_number_of_units_is_not_added() -> None:
    assert total_of((2, "10", "10"), (3, "20", "20")) == D("30")


# --- trace ------------------------------------------------------------------------------------


def test_produces_one_artifact_of_the_output_kind() -> None:
    result = capability().compute((properties(*column("24000", "6000")),))

    assert result.outputs == (Artifact(SHORT_TERM_RENTAL_GROSS_RENTS, D("30000")),)


def test_records_one_trace_line_naming_each_amount_in_order() -> None:
    result = capability().compute((properties(*column("24000", "6000")),))

    assert result.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_GROSS_RENTS,
            RENTAL_PROPERTY_SHORT_TERM_RENTS,
            (D("24000"), D("6000")),
            D("30000"),
        ),
    )


def test_records_one_trace_line_for_no_properties() -> None:
    result = capability().compute((properties(),))

    assert result.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_GROSS_RENTS, RENTAL_PROPERTY_SHORT_TERM_RENTS, (), D("0")
        ),
    )


def test_records_one_trace_line_whatever_the_number_of_properties() -> None:
    for amounts in ((), ("1",), ("1", "2"), ("1", "2", "3", "4")):
        assert len(capability().compute((properties(*column(*amounts)),)).trace) == 1


def test_the_trace_keeps_the_callers_order_not_the_sorted_one() -> None:
    (line,) = capability().compute((properties(*column("6000", "24000")),)).trace

    assert isinstance(line, RecordTotalLine)
    assert line.amounts == (D("6000"), D("24000"))


def test_its_trace_reads_item_by_item_in_english() -> None:
    result = capability().compute((properties(*column("24000", "6000")),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "short_term_rental_gross_rents: item 1 rental_property_short_term_rents 24000 "
        "+ item 2 rental_property_short_term_rents 6000 = 30000",
    )


def test_its_trace_for_no_properties_says_no_items() -> None:
    result = capability().compute((properties(),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "short_term_rental_gross_rents: no items = 0",
    )


def test_needs_its_properties() -> None:
    with pytest.raises(MissingArtifactError, match="ShortTermRentalGrossRents"):
        capability().compute(())


def test_does_not_consume_anything_else() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("1"))

    result = capability().compute((other, properties(*column("24000"))))

    assert result.outputs == (Artifact(SHORT_TERM_RENTAL_GROSS_RENTS, D("24000")),)


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (properties(*column("24000", "6000")),)

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
        name="ca/short_term_rental_gross_rents",
        params={},
        consumes={"properties": "ca/rental_properties"},
        produces={"output": "ca/short_term_rental_gross_rents"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/rental_properties"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ca/short_term_rental_gross_rents",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (RENTAL_PROPERTIES, SHORT_TERM_RENTAL_GROSS_RENTS):
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
    assert isinstance(built, ShortTermRentalGrossRents)
    assert built.consumes == frozenset({RENTAL_PROPERTIES})
    assert built.produces == frozenset({SHORT_TERM_RENTAL_GROSS_RENTS})


def test_a_computation_gives_the_total() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, properties(*column("24000", "6000"))
    )["ca-on/return"][0]

    assert worksheet.get(SHORT_TERM_RENTAL_GROSS_RENTS).value == D("30000")
    assert isinstance(
        worksheet.producer_of(SHORT_TERM_RENTAL_GROSS_RENTS), ShortTermRentalGrossRents
    )
    assert worksheet.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_GROSS_RENTS,
            RENTAL_PROPERTY_SHORT_TERM_RENTS,
            (D("24000"), D("6000")),
            D("30000"),
        ),
    )


def test_a_computation_with_no_properties_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, properties())["ca-on/return"][0]

    assert worksheet.get(SHORT_TERM_RENTAL_GROSS_RENTS).value == D("0")


# --- a row's short-term rents at most its gross rents -----------------------------------------
# Form T776 Part 3: the rents for short-term rentals of a property are part of its gross rents for
# all units, so a row whose short-term rents are above its gross rents is an input error, refused
# and not capped. Equal is valid, as is a row with no rents.


def test_a_row_with_short_term_rents_above_its_gross_rents_is_refused_naming_the_item() -> None:
    with pytest.raises(
        InputAboveBoundError,
        match=(
            r"item 1: ca/rental_property_short_term_rents 6001 is above "
            r"ca/rental_property_gross_rents 6000"
        ),
    ):
        total_of((2, "6001", "6000"))


def test_the_row_refused_is_named_by_its_position() -> None:
    with pytest.raises(
        InputAboveBoundError,
        match=r"item 2: ca/rental_property_short_term_rents 7000 is above",
    ):
        total_of((2, "1", "9"), (1, "7000", "6000"), (2, "2", "2"))


def test_a_row_with_short_term_rents_far_above_its_gross_rents_is_refused_not_added() -> None:
    with pytest.raises(InputAboveBoundError):
        total_of((2, "99999", "0"))


def test_equal_short_term_rents_and_gross_rents_are_valid() -> None:
    assert total_of((2, "6000", "6000")) == D("6000")


def test_a_row_with_no_rents_is_valid() -> None:
    assert total_of((2, "0", "0")) == D("0")


def test_a_row_with_short_term_rents_and_no_gross_rents_is_refused() -> None:
    with pytest.raises(InputAboveBoundError, match=r"item 1: .*rental_property_short_term_rents"):
        total_of((2, "1", "0"))


def test_every_row_is_checked_not_only_the_first() -> None:
    with pytest.raises(InputAboveBoundError, match=r"item 3: "):
        total_of((2, "1", "2"), (2, "3", "4"), (2, "5", "4"))


def test_the_row_check_refuses_before_the_total_is_produced() -> None:
    with pytest.raises(InputAboveBoundError):
        capability().compute((properties((2, "6001", "6000")),))


def test_a_valid_row_check_leaves_the_trace_as_it_was() -> None:
    result = capability().compute((properties((2, "6000", "6000"), (1, "24000", "30000")),))

    assert result.trace == (
        RecordTotalLine(
            SHORT_TERM_RENTAL_GROSS_RENTS,
            RENTAL_PROPERTY_SHORT_TERM_RENTS,
            (D("6000"), D("24000")),
            D("30000"),
        ),
    )
