"""Shared helpers for the foreign tax countries totals of Form T691 Part 4: the records and cases.

Each of the three capabilities totals one figure of the Form T2209 country records (non-business
tax paid, net foreign non-business income, business tax paid) over every record of the list. They
differ only in the figure they total, so the cases they share are the methods of
`ForeignTaxCountriesTotalCases`; each test module subclasses it with its own capability and figure.
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
from tax_engine.domain.errors import InvalidCapabilityError, MissingArtifactError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import NO_ROUNDING
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemsTotalLine
from tax_engine.jurisdictions.ca.catalog import FOREIGN_TAX_COUNTRIES
from tests.manifest_support import required_inputs

D = Decimal

# Made up for this test and not registered: the total a capability produces.
TOTAL = ArtifactKind("ex/foreign_tax_countries_total", Decimal)


def country(field: ArtifactKind[Any], amount: str) -> dict[Any, Any]:
    """One country record: `amount` in `field` and 0 in each of the other figures."""
    return {**{each: D(0) for each in FOREIGN_TAX_COUNTRIES.fields}, field: D(amount)}


def other_field(field: ArtifactKind[Any]) -> ArtifactKind[Any]:
    return next(each for each in FOREIGN_TAX_COUNTRIES.fields if each is not field)


def countries(*rows: dict[Any, Any]) -> Artifact[Any]:
    return Artifact(FOREIGN_TAX_COUNTRIES, RecordList(FOREIGN_TAX_COUNTRIES.fields, rows))


def compute(capability_class: Any, *rows: dict[Any, Any]) -> Any:
    return capability_class(FOREIGN_TAX_COUNTRIES, TOTAL).compute((countries(*rows),))


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
    """The service over a manifest of the one capability `identifier`, reading the country list."""
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name=identifier,
        params={},
        consumes={"countries": "ca/foreign_tax_countries"},
        produces={"output": "ex/foreign_tax_countries_total"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/foreign_tax_countries"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/foreign_tax_countries_total",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (FOREIGN_TAX_COUNTRIES, TOTAL):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _NoParameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


class ForeignTaxCountriesTotalCases:
    """The cases of a foreign tax countries total, for the subclass's own capability and figure.

    A subclass sets `CAPABILITY`, `IDENTIFIER`, `MODULE` (its name in the capabilities package),
    and `FIELD` (the figure of each country record it totals).
    """

    CAPABILITY: Any
    IDENTIFIER: str
    MODULE: str
    FIELD: ArtifactKind[Any]

    def own(self, amount: str) -> dict[Any, Any]:
        """A country record with `amount` in this capability's figure and 0 in the others."""
        return country(self.FIELD, amount)

    def elsewhere(self, amount: str) -> dict[Any, Any]:
        """A country record with `amount` in another figure, so this capability's figure is 0."""
        return country(other_field(self.FIELD), amount)

    # --- registration and slots ---------------------------------------------------------------

    def test_is_exported_from_the_canada_capabilities_package(self) -> None:
        assert canada.NAMESPACE == "ca"
        assert self.MODULE in canada.__all__
        assert getattr(canada, self.MODULE).__dict__[self.CAPABILITY.__name__] is self.CAPABILITY

    def test_is_registered_under_its_identifier(self) -> None:
        assert tax_engine.jurisdictions.ca.capabilities is canada
        assert CapabilityRegistry.shared().get(self.IDENTIFIER) is self.CAPABILITY

    def test_declares_its_contract(self) -> None:
        wired = self.CAPABILITY(FOREIGN_TAX_COUNTRIES, TOTAL)

        assert wired.consumes == frozenset({FOREIGN_TAX_COUNTRIES})
        assert wired.produces == frozenset({TOTAL})

    def test_leaves_its_contract_to_the_base(self) -> None:
        assert "consumes" not in vars(self.CAPABILITY)
        assert "produces" not in vars(self.CAPABILITY)

    def test_declares_its_figure(self) -> None:
        assert self.CAPABILITY.FIELD is self.FIELD

    def test_declares_its_slots(self) -> None:
        assert self.CAPABILITY.PARAMETERS == {}
        assert self.CAPABILITY.CONSUMES == {"countries": RecordList}
        assert self.CAPABILITY.PRODUCES == {"output": Decimal}
        assert not self.CAPABILITY.is_list_slot("countries")

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
        wired = self.CAPABILITY(countries=FOREIGN_TAX_COUNTRIES, output=TOTAL)

        (output,) = wired.compute((countries(self.own("100")),)).outputs

        assert output == Artifact(TOTAL, D("100"))

    def test_takes_no_parameter_dataset(self) -> None:
        with pytest.raises(TypeError):
            self.CAPABILITY(FOREIGN_TAX_COUNTRIES, TOTAL, object())

    def test_mypy_rejects_a_dataset_it_has_no_slot_for(self) -> None:
        def wire() -> None:  # type-checked, never run
            # It has no parameter slot, so a dataset is one argument too many; the ignore fails
            # under mypy (warn_unused_ignores) if it is ever accepted.
            rate = ParameterDataset(
                "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
            )
            self.CAPABILITY(FOREIGN_TAX_COUNTRIES, TOTAL, rate)

        assert callable(wire)

    def test_refuses_a_money_kind_for_its_record_list(self) -> None:
        with pytest.raises(InvalidCapabilityError, match=self.CAPABILITY.__name__) as raised:
            self.CAPABILITY(ArtifactKind("ex/not_a_list", Decimal), TOTAL)

        assert "'countries'" in str(raised.value)

    def test_refuses_a_count_kind_for_its_output(self) -> None:
        with pytest.raises(InvalidCapabilityError, match=self.CAPABILITY.__name__) as raised:
            self.CAPABILITY(FOREIGN_TAX_COUNTRIES, ArtifactKind("ex/a_count", int))

        assert "'output'" in str(raised.value)

    def test_is_not_generic_over_artifacts(self) -> None:
        assert not getattr(self.CAPABILITY, "__type_params__", ())
        assert not getattr(self.CAPABILITY, "__parameters__", ())

    # --- computing ----------------------------------------------------------------------------

    def test_totals_its_figure_over_every_country(self) -> None:
        assert total(self.CAPABILITY, self.own("30000"), self.own("7500")) == D("37500")

    def test_one_country_totals_its_own_figure(self) -> None:
        assert total(self.CAPABILITY, self.own("60000")) == D("60000")

    def test_a_country_with_another_figure_only_adds_nothing(self) -> None:
        assert total(self.CAPABILITY, self.elsewhere("40000")) == D("0")

    def test_reads_only_its_own_figure_of_each_country(self) -> None:
        row = {
            **self.own("500"),
            **{each: D("7777") for each in FOREIGN_TAX_COUNTRIES.fields if each is not self.FIELD},
        }

        assert total(self.CAPABILITY, row) == D("500")

    def test_an_empty_list_totals_zero(self) -> None:
        assert total(self.CAPABILITY) == D("0")

    def test_keeps_the_cents_and_never_rounds(self) -> None:
        rows = (self.own("100.10"), self.own("50.05"), self.own("0.015"))

        assert total(self.CAPABILITY, *rows) == D("150.165")

    def test_needs_its_record_list(self) -> None:
        with pytest.raises(MissingArtifactError):
            self.CAPABILITY(FOREIGN_TAX_COUNTRIES, TOTAL).compute(())

    def test_has_one_output(self) -> None:
        result = self.CAPABILITY(FOREIGN_TAX_COUNTRIES, TOTAL).compute((countries(),))

        assert result.outputs == (Artifact(TOTAL, D("0")),)

    def test_compute_is_repeatable(self) -> None:
        wired = self.CAPABILITY(FOREIGN_TAX_COUNTRIES, TOTAL)
        inputs = (countries(self.own("60000"), self.own("30000")),)

        assert wired.compute(inputs) == wired.compute(inputs)

    # --- trace --------------------------------------------------------------------------------

    def test_records_only_an_empty_total_for_no_countries(self) -> None:
        assert lines(self.CAPABILITY) == (ItemsTotalLine(output=TOTAL, items=(), total=D("0")),)

    def test_records_each_country_by_position_then_the_total(self) -> None:
        rows = (self.own("60000"), self.elsewhere("40000"), self.own("30000"))

        assert lines(self.CAPABILITY, *rows) == (
            ItemsTotalLine(
                output=TOTAL,
                items=((1, D("60000")), (2, D("0")), (3, D("30000"))),
                total=D("90000"),
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
        assert built.consumes == frozenset({FOREIGN_TAX_COUNTRIES})
        assert built.produces == frozenset({TOTAL})

    def test_a_computation_gives_the_total_and_its_trace(self) -> None:
        rows = (self.own("60000"), self.elsewhere("40000"))

        worksheet = service(self.IDENTIFIER).compute(
            JurisdictionCode("CA-ON"), 2025, countries(*rows)
        )["ca-on/return"][0]

        assert worksheet.get(TOTAL).value == D("60000")
        assert isinstance(worksheet.producer_of(TOTAL), self.CAPABILITY)
        assert worksheet.trace == (
            ItemsTotalLine(output=TOTAL, items=((1, D("60000")), (2, D("0"))), total=D("60000")),
        )

    def test_a_computation_with_no_countries_gives_zero(self) -> None:
        worksheet = service(self.IDENTIFIER).compute(JurisdictionCode("CA-ON"), 2025, countries())[
            "ca-on/return"
        ][0]

        assert worksheet.get(TOTAL).value == D("0")
