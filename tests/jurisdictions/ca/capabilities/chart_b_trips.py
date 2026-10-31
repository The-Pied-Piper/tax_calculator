"""Shared helpers for the Chart B zone total tests of Form T2222: trips, totals and trace lines.

The Zone A and Zone B capabilities differ only in the zone they total, so the cases they share are
the methods of `ZoneTotalCases`; each test module subclasses it with its own capability and zones.
The figures are CRA's own, from the form's examples 3 and 4.
"""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest

import tax_engine.jurisdictions.ca
import tax_engine.jurisdictions.ca.capabilities as canada
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    InvalidCapabilityError,
    InvalidRecordError,
    MissingArtifactError,
    NotFoundError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import NO_ROUNDING
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemLesserOfLine, ItemsTotalLine
from tax_engine.jurisdictions.ca.catalog import (
    TRAVEL_INDIVIDUAL,
    TRAVEL_TRIPS,
    TRIP_BENEFIT_OR_STANDARD_AMOUNT,
    TRIP_LOWEST_RETURN_AIRFARE,
    TRIP_TRAVEL_EXPENSES,
    TRIP_ZONE,
)
from tests.manifest_support import required_inputs

D = Decimal
ZONE_A = 1
ZONE_B = 2

# Made up for this test and not registered: the total a capability produces.
TOTAL = ArtifactKind("ex/zone_total", Decimal)


def trip(individual: int, zone: int, column_3: str, column_4: str, column_5: str) -> dict[Any, Any]:
    return {
        TRAVEL_INDIVIDUAL: individual,
        TRIP_ZONE: zone,
        TRIP_BENEFIT_OR_STANDARD_AMOUNT: D(column_3),
        TRIP_TRAVEL_EXPENSES: D(column_4),
        TRIP_LOWEST_RETURN_AIRFARE: D(column_5),
    }


def trips(*rows: dict[Any, Any]) -> Artifact[Any]:
    return Artifact(TRAVEL_TRIPS, RecordList(TRAVEL_TRIPS.fields, rows))


def total(capability_class: Any, *rows: dict[Any, Any]) -> Decimal:
    (output,) = capability_class(TRAVEL_TRIPS, TOTAL).compute((trips(*rows),)).outputs
    assert output.kind == TOTAL
    value: Decimal = output.value
    return value


def lines(capability_class: Any, *rows: dict[Any, Any]) -> tuple[Any, ...]:
    return tuple(capability_class(TRAVEL_TRIPS, TOTAL).compute((trips(*rows),)).trace)


def line(position: int, column_3: str, column_4: str, column_5: str, lowest: str) -> Any:
    return ItemLesserOfLine(
        output=TOTAL,
        position=position,
        parts=(
            (TRIP_BENEFIT_OR_STANDARD_AMOUNT, D(column_3)),
            (TRIP_TRAVEL_EXPENSES, D(column_4)),
            (TRIP_LOWEST_RETURN_AIRFARE, D(column_5)),
        ),
        result=D(lowest),
    )


# Example 4: the family's five non-medical trips, individual 1 (yourself) twice, individual 2
# (the spouse) twice and individual 3 (the child) once. The example does not say which zone
# Whitehorse is in, so these tests put every trip in the zone under test.
EXAMPLE_4 = (
    (1, "1500", "1300", "750", "750"),
    (1, "1500", "800", "900", "800"),
    (2, "400", "400", "600", "400"),
    (2, "800", "850", "900", "800"),
    (3, "1200", "1500", "900", "900"),
)


def example_4(zone: int) -> tuple[dict[Any, Any], ...]:
    return tuple(trip(i, zone, c3, c4, c5) for i, c3, c4, c5, _ in EXAMPLE_4)


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _NoParameters:
    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service(identifier: str) -> TaxComputationService:
    """The service over a manifest of the one capability `identifier`, reading ca/travel_trips."""
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name=identifier,
        params={},
        consumes={"trips": "ca/travel_trips"},
        produces={"total": "ex/zone_total"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/travel_trips"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/zone_total",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (TRAVEL_TRIPS, TOTAL):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _NoParameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


class ZoneTotalCases:
    """The cases of a Chart B zone total, for the subclass's own capability and zones.

    A subclass sets `CAPABILITY`, `IDENTIFIER`, `MODULE` (its name in the capabilities package),
    `OWN_ZONE` and `OTHER_ZONE`, and `MIXED_TOTAL`, the total of Example 4's five trips when the
    first two are in Zone A and the other three in Zone B.
    """

    CAPABILITY: Any
    IDENTIFIER: str
    MODULE: str
    OWN_ZONE: int
    OTHER_ZONE: int
    MIXED_TOTAL: str

    # --- registration and slots ---------------------------------------------------------------

    def test_is_exported_from_the_canada_capabilities_package(self) -> None:
        assert canada.NAMESPACE == "ca"
        assert self.MODULE in canada.__all__
        assert getattr(canada, self.MODULE).__dict__[self.CAPABILITY.__name__] is self.CAPABILITY

    def test_is_registered_under_its_identifier(self) -> None:
        assert tax_engine.jurisdictions.ca.capabilities is canada
        assert CapabilityRegistry.shared().get(self.IDENTIFIER) is self.CAPABILITY

    def test_declares_its_contract(self) -> None:
        wired = self.CAPABILITY(TRAVEL_TRIPS, TOTAL)

        assert wired.consumes == frozenset({TRAVEL_TRIPS})
        assert wired.produces == frozenset({TOTAL})

    def test_leaves_its_contract_to_the_base(self) -> None:
        assert "consumes" not in vars(self.CAPABILITY)
        assert "produces" not in vars(self.CAPABILITY)

    def test_declares_its_slots(self) -> None:
        assert self.CAPABILITY.PARAMETERS == {}
        assert self.CAPABILITY.CONSUMES == {"trips": RecordList}
        assert self.CAPABILITY.PRODUCES == {"total": Decimal}
        assert not self.CAPABILITY.is_list_slot("trips")

    def test_its_slots_are_read_only(self) -> None:
        for slots in (
            self.CAPABILITY.PARAMETERS,
            self.CAPABILITY.CONSUMES,
            self.CAPABILITY.PRODUCES,
        ):
            assert isinstance(slots, MappingProxyType)
            with pytest.raises(TypeError):
                cast(Any, slots)["extra"] = Decimal

    def test_is_built_from_its_slot_names_as_keywords(self) -> None:
        wired = self.CAPABILITY(trips=TRAVEL_TRIPS, total=TOTAL)

        (output,) = wired.compute((trips(trip(1, self.OWN_ZONE, "100", "200", "300")),)).outputs

        assert output == Artifact(TOTAL, D("100"))

    def test_takes_no_parameter_dataset(self) -> None:
        with pytest.raises(TypeError):
            self.CAPABILITY(TRAVEL_TRIPS, TOTAL, object())

    def test_mypy_rejects_a_dataset_it_has_no_slot_for(self) -> None:
        def wire() -> None:  # type-checked, never run
            # It has no parameter slot, so a dataset is one argument too many; the ignore fails
            # under mypy (warn_unused_ignores) if it is ever accepted.
            rate = ParameterDataset(
                "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
            )
            self.CAPABILITY(TRAVEL_TRIPS, TOTAL, rate)

        assert callable(wire)

    def test_refuses_a_money_kind_for_its_record_list(self) -> None:
        with pytest.raises(InvalidCapabilityError, match=self.CAPABILITY.__name__) as raised:
            self.CAPABILITY(ArtifactKind("ex/not_a_list", Decimal), TOTAL)

        assert "'trips'" in str(raised.value)

    def test_refuses_a_count_kind_for_its_total(self) -> None:
        with pytest.raises(InvalidCapabilityError, match=self.CAPABILITY.__name__) as raised:
            self.CAPABILITY(TRAVEL_TRIPS, ArtifactKind("ex/a_count", int))

        assert "'total'" in str(raised.value)

    def test_is_not_generic_over_artifacts(self) -> None:
        assert not getattr(self.CAPABILITY, "__type_params__", ())
        assert not getattr(self.CAPABILITY, "__parameters__", ())

    # --- computing ----------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("column_3", "column_4", "column_5", "lowest"),
        [
            # Example 3: "the value of the allowance received from Smith Co.: $5,000 (column 3)",
            # "the actual amount of your trip: $1,500 (column 4)" and the lowest return airfare of
            # $400 (column 5): "you enter $400 under the "Zone A" column".
            ("5000", "1500", "400", "400"),
            ("300", "1500", "400", "300"),
            ("5000", "250", "400", "250"),
            ("5000", "1500", "5000", "1500"),
            ("700", "700", "700", "700"),
            ("0", "1500", "400", "0"),
        ],
    )
    def test_takes_the_lowest_of_columns_3_4_and_5_for_a_trip_in_its_zone(
        self, column_3: str, column_4: str, column_5: str, lowest: str
    ) -> None:
        row = trip(1, self.OWN_ZONE, column_3, column_4, column_5)

        assert total(self.CAPABILITY, row) == D(lowest)

    def test_a_trip_in_the_other_zone_adds_nothing(self) -> None:
        assert total(self.CAPABILITY, trip(1, self.OTHER_ZONE, "5000", "1500", "400")) == D("0")

    def test_totals_the_lowest_amounts_of_the_five_trips_of_example_4(self) -> None:
        # Trip 1 750, trip 2 800, the spouse's trip 1 400 and trip 2 800 and the child's trip 900,
        # as the example works each out: 750 + 800 + 400 + 800 + 900 = 3650.
        assert total(self.CAPABILITY, *example_4(self.OWN_ZONE)) == D("3650")
        assert total(self.CAPABILITY, *example_4(self.OTHER_ZONE)) == D("0")

    def test_a_trip_for_each_individual_counts_the_same(self) -> None:
        # The individual is only named: the same trip for individual 1 or for individual 4.
        assert total(self.CAPABILITY, trip(1, self.OWN_ZONE, "100", "200", "300")) == total(
            self.CAPABILITY, trip(4, self.OWN_ZONE, "100", "200", "300")
        )

    def test_any_number_of_trips_are_totalled_without_a_limit(self) -> None:
        # "You can also claim any number of medical trips": four trips by one individual, each at
        # its lowest amount (300, 1000, 1200 and 1200), and no cap of two trips or of $1,200 on
        # the total.
        rows = (
            trip(1, self.OWN_ZONE, "500", "2000", "300"),
            trip(1, self.OWN_ZONE, "5000", "1000", "1200"),
            trip(1, self.OWN_ZONE, "1200", "1200", "1500"),
            trip(1, self.OWN_ZONE, "1200", "1600", "2000"),
        )

        assert total(self.CAPABILITY, *rows) == D("3700")

    def test_keeps_the_cents_and_never_rounds(self) -> None:
        rows = (
            trip(1, self.OWN_ZONE, "100.10", "200", "300"),
            trip(2, self.OWN_ZONE, "50.05", "20.015", "300"),
        )

        assert total(self.CAPABILITY, *rows) == D("120.115")

    def test_no_trips_total_nothing(self) -> None:
        assert total(self.CAPABILITY) == D("0")

    def test_totals_only_its_own_trips_among_both_zones(self) -> None:
        # Example 4's trips, the first two (750 and 800) in Zone A and the other three (400, 800
        # and 900) in Zone B: A is 750 + 800 = 1550 and B is 400 + 800 + 900 = 2100.
        rows = tuple(
            trip(i, ZONE_A if n < 2 else ZONE_B, c3, c4, c5)
            for n, (i, c3, c4, c5, _) in enumerate(EXAMPLE_4)
        )

        assert total(self.CAPABILITY, *rows) == D(self.MIXED_TOTAL)

    def test_refuses_a_trip_in_neither_zone_whichever_zone_the_capability_is_for(self) -> None:
        with pytest.raises(InvalidRecordError, match=r"item 1.*trip_zone"):
            total(self.CAPABILITY, trip(1, 3, "100", "200", "300"))

    @pytest.mark.parametrize("zone", [0, 3, 12])
    def test_refuses_a_trip_in_neither_zone_naming_its_position_and_field(self, zone: int) -> None:
        rows = (trip(1, self.OWN_ZONE, "100", "200", "300"), trip(1, zone, "100", "200", "300"))

        with pytest.raises(InvalidRecordError, match=r"item 2.*trip_zone"):
            total(self.CAPABILITY, *rows)

    def test_needs_its_record_list(self) -> None:
        with pytest.raises(MissingArtifactError):
            self.CAPABILITY(TRAVEL_TRIPS, TOTAL).compute(())

    def test_has_one_output(self) -> None:
        result = self.CAPABILITY(TRAVEL_TRIPS, TOTAL).compute((trips(),))

        assert result.outputs == (Artifact(TOTAL, D("0")),)

    # --- trace --------------------------------------------------------------------------------

    def test_records_only_an_empty_total_for_no_trips(self) -> None:
        assert lines(self.CAPABILITY) == (ItemsTotalLine(output=TOTAL, items=(), total=D("0")),)

    def test_records_each_trip_in_its_zone_by_its_position_then_the_total(self) -> None:
        rows = (
            trip(1, self.OWN_ZONE, "1500", "1300", "750"),
            trip(2, self.OTHER_ZONE, "400", "400", "600"),
            trip(1, self.OWN_ZONE, "1500", "800", "900"),
        )

        assert lines(self.CAPABILITY, *rows) == (
            line(1, "1500", "1300", "750", "750"),
            line(3, "1500", "800", "900", "800"),
            ItemsTotalLine(output=TOTAL, items=((1, D("750")), (3, D("800"))), total=D("1550")),
        )

    def test_records_nothing_but_a_zero_total_when_every_trip_is_in_the_other_zone(self) -> None:
        rows = (trip(1, self.OTHER_ZONE, "1500", "1300", "750"),)

        assert lines(self.CAPABILITY, *rows) == (
            ItemsTotalLine(output=TOTAL, items=(), total=D("0")),
        )

    def test_the_last_trace_line_amount_is_the_output(self) -> None:
        trace = lines(self.CAPABILITY, *example_4(self.OWN_ZONE))

        assert trace[-1].amount == total(self.CAPABILITY, *example_4(self.OWN_ZONE))

    def test_compute_is_repeatable(self) -> None:
        wired = self.CAPABILITY(TRAVEL_TRIPS, TOTAL)
        inputs = (trips(*example_4(self.OWN_ZONE)),)

        assert wired.compute(inputs) == wired.compute(inputs)

    # --- through TaxComputationService --------------------------------------------------------

    def test_a_computation_builds_the_capability_from_the_registry(self) -> None:
        composition = (
            service(self.IDENTIFIER)
            .compose(JurisdictionCode("CA-ON"), 2025)
            .form("ca-on/return")
            .composition
        )

        (built,) = composition.order
        assert isinstance(built, self.CAPABILITY)
        assert built.consumes == frozenset({TRAVEL_TRIPS})
        assert built.produces == frozenset({TOTAL})

    def test_a_computation_gives_the_zone_total_and_its_trace(self) -> None:
        rows = (
            trip(1, self.OWN_ZONE, "1500", "1300", "750"),
            trip(2, self.OTHER_ZONE, "400", "400", "600"),
            trip(1, self.OWN_ZONE, "1500", "800", "900"),
        )

        worksheet = service(self.IDENTIFIER).compute(JurisdictionCode("CA-ON"), 2025, trips(*rows))[
            "ca-on/return"
        ][0]

        assert worksheet.get(TOTAL).value == D("1550")
        assert isinstance(worksheet.producer_of(TOTAL), self.CAPABILITY)
        assert worksheet.trace == (
            line(1, "1500", "1300", "750", "750"),
            line(3, "1500", "800", "900", "800"),
            ItemsTotalLine(output=TOTAL, items=((1, D("750")), (3, D("800"))), total=D("1550")),
        )

    def test_a_computation_with_no_trips_gives_zero(self) -> None:
        worksheet = service(self.IDENTIFIER).compute(JurisdictionCode("CA-ON"), 2025, trips())[
            "ca-on/return"
        ][0]

        assert worksheet.get(TOTAL).value == D("0")

    def test_a_computation_refuses_a_trip_in_neither_zone(self) -> None:
        with pytest.raises(InvalidRecordError, match=r"item 1.*trip_zone"):
            service(self.IDENTIFIER).compute(
                JurisdictionCode("CA-ON"), 2025, trips(trip(1, 3, "100", "200", "300"))
            )
