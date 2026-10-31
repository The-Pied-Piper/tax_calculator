"""Shared helpers for the Chart B province totals of Form T2043: the province list and the cases.

Each of the sixteen capabilities totals one line (row 1, gross income, or row 4, salaries and
wages) over the rows of one designated province of the statement's province list. They differ
only in the province and the line, so the cases they share are the methods of `ProvinceTotalCases`;
each test module subclasses it with its own capability, province and line.
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
from tax_engine.domain.trace import ItemsTotalLine
from tax_engine.jurisdictions.ca.catalog import (
    FARM_CHART_B_PROVINCE,
    FARM_CHART_B_PROVINCE_GROSS_INCOME,
    FARM_CHART_B_PROVINCE_SALARIES,
    FARM_CHART_B_PROVINCES,
)
from tests.manifest_support import required_inputs

D = Decimal

# Made up for this test and not registered: the total a capability produces.
TOTAL = ArtifactKind("ex/chart_b_province_total", Decimal)

# The eight designated provinces, in the form's order, and a few codes that name none.
PROVINCE_CODES = range(1, 9)
NOT_A_PROVINCE = (0, 9)


def record(code: int, gross: str, salaries: str) -> dict[Any, Any]:
    """One row of the province list: its code, row 1 gross income and row 4 salaries."""
    return {
        FARM_CHART_B_PROVINCE: code,
        FARM_CHART_B_PROVINCE_GROSS_INCOME: D(gross),
        FARM_CHART_B_PROVINCE_SALARIES: D(salaries),
    }


def provinces(*rows: dict[Any, Any]) -> Artifact[Any]:
    return Artifact(FARM_CHART_B_PROVINCES, RecordList(FARM_CHART_B_PROVINCES.fields, rows))


def compute(capability_class: Any, *rows: dict[Any, Any]) -> Any:
    return capability_class(FARM_CHART_B_PROVINCES, TOTAL).compute((provinces(*rows),))


def total(capability_class: Any, *rows: dict[Any, Any]) -> Decimal:
    (output,) = compute(capability_class, *rows).outputs
    assert output.kind == TOTAL
    value: Decimal = output.value
    return value


def lines(capability_class: Any, *rows: dict[Any, Any]) -> tuple[Any, ...]:
    return tuple(compute(capability_class, *rows).trace)


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _NoParameters:
    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service(identifier: str) -> TaxComputationService:
    """The service over a manifest of the one capability `identifier`, reading the province list."""
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name=identifier,
        params={},
        consumes={"provinces": "ca/farm_chart_b_provinces"},
        produces={"output": "ex/chart_b_province_total"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/farm_chart_b_provinces"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/chart_b_province_total",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (FARM_CHART_B_PROVINCES, TOTAL):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _NoParameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


class ProvinceTotalCases:
    """The cases of a Chart B province total, for the subclass's own capability and province.

    A subclass sets `CAPABILITY`, `IDENTIFIER`, `MODULE` (its name in the capabilities package),
    `PROVINCE` (its code, 1 to 8), and `FIELD` (the amount it totals: row 1 or row 4).
    """

    CAPABILITY: Any
    IDENTIFIER: str
    MODULE: str
    PROVINCE: int
    FIELD: ArtifactKind[Any]

    def own(self, amount: str) -> dict[Any, Any]:
        """A row for this capability's province, with `amount` in its line and 0 in the other."""
        other = (
            FARM_CHART_B_PROVINCE_SALARIES
            if self.FIELD is FARM_CHART_B_PROVINCE_GROSS_INCOME
            else FARM_CHART_B_PROVINCE_GROSS_INCOME
        )
        return {FARM_CHART_B_PROVINCE: self.PROVINCE, self.FIELD: D(amount), other: D("0")}

    def other_province(self) -> int:
        return next(code for code in PROVINCE_CODES if code != self.PROVINCE)

    # --- registration and slots ---------------------------------------------------------------

    def test_is_exported_from_the_canada_capabilities_package(self) -> None:
        assert canada.NAMESPACE == "ca"
        assert self.MODULE in canada.__all__
        assert getattr(canada, self.MODULE).__dict__[self.CAPABILITY.__name__] is self.CAPABILITY

    def test_is_registered_under_its_identifier(self) -> None:
        assert tax_engine.jurisdictions.ca.capabilities is canada
        assert CapabilityRegistry.shared().get(self.IDENTIFIER) is self.CAPABILITY

    def test_declares_its_contract(self) -> None:
        wired = self.CAPABILITY(FARM_CHART_B_PROVINCES, TOTAL)

        assert wired.consumes == frozenset({FARM_CHART_B_PROVINCES})
        assert wired.produces == frozenset({TOTAL})

    def test_leaves_its_contract_to_the_base(self) -> None:
        assert "consumes" not in vars(self.CAPABILITY)
        assert "produces" not in vars(self.CAPABILITY)

    def test_declares_its_province_and_line(self) -> None:
        assert self.CAPABILITY.PROVINCE == self.PROVINCE
        assert self.CAPABILITY.FIELD is self.FIELD

    def test_declares_its_slots(self) -> None:
        assert self.CAPABILITY.PARAMETERS == {}
        assert self.CAPABILITY.CONSUMES == {"provinces": RecordList}
        assert self.CAPABILITY.PRODUCES == {"output": Decimal}
        assert not self.CAPABILITY.is_list_slot("provinces")

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
        wired = self.CAPABILITY(provinces=FARM_CHART_B_PROVINCES, output=TOTAL)

        (output,) = wired.compute((provinces(self.own("100")),)).outputs

        assert output == Artifact(TOTAL, D("100"))

    def test_takes_no_parameter_dataset(self) -> None:
        with pytest.raises(TypeError):
            self.CAPABILITY(FARM_CHART_B_PROVINCES, TOTAL, object())

    def test_mypy_rejects_a_dataset_it_has_no_slot_for(self) -> None:
        def wire() -> None:  # type-checked, never run
            # It has no parameter slot, so a dataset is one argument too many; the ignore fails
            # under mypy (warn_unused_ignores) if it is ever accepted.
            rate = ParameterDataset(
                "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
            )
            self.CAPABILITY(FARM_CHART_B_PROVINCES, TOTAL, rate)

        assert callable(wire)

    def test_refuses_a_money_kind_for_its_record_list(self) -> None:
        with pytest.raises(InvalidCapabilityError, match=self.CAPABILITY.__name__) as raised:
            self.CAPABILITY(ArtifactKind("ex/not_a_list", Decimal), TOTAL)

        assert "'provinces'" in str(raised.value)

    def test_refuses_a_count_kind_for_its_output(self) -> None:
        with pytest.raises(InvalidCapabilityError, match=self.CAPABILITY.__name__) as raised:
            self.CAPABILITY(FARM_CHART_B_PROVINCES, ArtifactKind("ex/a_count", int))

        assert "'output'" in str(raised.value)

    def test_is_not_generic_over_artifacts(self) -> None:
        assert not getattr(self.CAPABILITY, "__type_params__", ())
        assert not getattr(self.CAPABILITY, "__parameters__", ())

    # --- computing ----------------------------------------------------------------------------

    def test_totals_the_rows_of_its_own_province(self) -> None:
        assert total(self.CAPABILITY, self.own("60000")) == D("60000")

    def test_a_row_for_another_province_adds_nothing(self) -> None:
        other = {**self.own("40000"), FARM_CHART_B_PROVINCE: self.other_province()}

        assert total(self.CAPABILITY, other) == D("0")

    def test_two_rows_for_its_province_add(self) -> None:
        rows = (self.own("30000"), record(self.other_province(), "1", "2"), self.own("7500"))

        assert total(self.CAPABILITY, *rows) == D("37500")

    def test_reads_only_its_own_line_of_each_row(self) -> None:
        # The other line of the row is not this capability's: it adds nothing.
        row = record(self.PROVINCE, "60000", "15000")

        if self.FIELD is FARM_CHART_B_PROVINCE_GROSS_INCOME:
            assert total(self.CAPABILITY, row) == D("60000")
        else:
            assert total(self.CAPABILITY, row) == D("15000")

    def test_an_empty_list_totals_zero(self) -> None:
        assert total(self.CAPABILITY) == D("0")

    def test_a_province_with_no_row_totals_zero(self) -> None:
        assert total(self.CAPABILITY, record(self.other_province(), "40000", "6000")) == D("0")

    def test_keeps_the_cents_and_never_rounds(self) -> None:
        rows = (self.own("100.10"), self.own("50.05"), self.own("0.015"))

        assert total(self.CAPABILITY, *rows) == D("150.165")

    @pytest.mark.parametrize("code", NOT_A_PROVINCE)
    def test_refuses_a_code_outside_one_to_eight_naming_its_item(self, code: int) -> None:
        rows = (self.own("100"), record(code, "1", "0"))

        with pytest.raises(InvalidRecordError, match=r"item 2.*farm_chart_b_province"):
            total(self.CAPABILITY, *rows)

    @pytest.mark.parametrize("code", NOT_A_PROVINCE)
    def test_refuses_a_code_outside_one_to_eight_even_for_another_province(self, code: int) -> None:
        with pytest.raises(InvalidRecordError, match=r"item 1.*farm_chart_b_province"):
            total(self.CAPABILITY, record(code, "1", "0"))

    def test_needs_its_record_list(self) -> None:
        with pytest.raises(MissingArtifactError):
            self.CAPABILITY(FARM_CHART_B_PROVINCES, TOTAL).compute(())

    def test_has_one_output(self) -> None:
        result = self.CAPABILITY(FARM_CHART_B_PROVINCES, TOTAL).compute((provinces(),))

        assert result.outputs == (Artifact(TOTAL, D("0")),)

    def test_compute_is_repeatable(self) -> None:
        wired = self.CAPABILITY(FARM_CHART_B_PROVINCES, TOTAL)
        inputs = (provinces(self.own("60000"), self.own("30000")),)

        assert wired.compute(inputs) == wired.compute(inputs)

    # --- trace --------------------------------------------------------------------------------

    def test_records_only_an_empty_total_for_no_rows(self) -> None:
        assert lines(self.CAPABILITY) == (ItemsTotalLine(output=TOTAL, items=(), total=D("0")),)

    def test_records_each_row_of_its_province_by_position_then_the_total(self) -> None:
        rows = (
            self.own("60000"),
            record(self.other_province(), "40000", "6000"),
            self.own("30000"),
        )

        assert lines(self.CAPABILITY, *rows) == (
            ItemsTotalLine(
                output=TOTAL, items=((1, D("60000")), (3, D("30000"))), total=D("90000")
            ),
        )

    def test_the_last_trace_line_amount_is_the_output(self) -> None:
        rows = (self.own("60000"), self.own("30000"))

        assert lines(self.CAPABILITY, *rows)[-1].amount == total(self.CAPABILITY, *rows)

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
        assert built.consumes == frozenset({FARM_CHART_B_PROVINCES})
        assert built.produces == frozenset({TOTAL})

    def test_a_computation_gives_the_province_total_and_its_trace(self) -> None:
        rows = (self.own("60000"), record(self.other_province(), "40000", "6000"))

        worksheet = service(self.IDENTIFIER).compute(
            JurisdictionCode("CA-ON"), 2025, provinces(*rows)
        )["ca-on/return"][0]

        assert worksheet.get(TOTAL).value == D("60000")
        assert isinstance(worksheet.producer_of(TOTAL), self.CAPABILITY)
        assert worksheet.trace == (
            ItemsTotalLine(output=TOTAL, items=((1, D("60000")),), total=D("60000")),
        )

    def test_a_computation_with_no_rows_gives_zero(self) -> None:
        worksheet = service(self.IDENTIFIER).compute(JurisdictionCode("CA-ON"), 2025, provinces())[
            "ca-on/return"
        ][0]

        assert worksheet.get(TOTAL).value == D("0")

    def test_a_computation_refuses_a_code_outside_one_to_eight(self) -> None:
        with pytest.raises(InvalidRecordError, match=r"item 1.*farm_chart_b_province"):
            service(self.IDENTIFIER).compute(
                JurisdictionCode("CA-ON"), 2025, provinces(record(9, "1", "0"))
            )
