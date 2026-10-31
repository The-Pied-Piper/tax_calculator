"""Unit tests for TaxComputationService: a manifest built into a set of forms (a `FormSet`), run.

The service does the I/O only: it reads the jurisdiction, takes the manifest for the tax year,
resolves each selection's class and datasets from the ports and registries it was given, has
`CapabilityBuilder` build each capability from them and the artifact registry (the builder resolves
artifact kinds), and builds the `Composition`. Resolution errors
propagate unchanged. The ports are small in-memory fakes and the registries private ones; every
code, capability, kind and dataset is made up.
"""

from __future__ import annotations

import decimal
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction as ExactFraction
from functools import cache
from typing import Any, ClassVar, assert_type

import pytest

from tax_engine.application.ports.jurisdiction_source import JurisdictionSource
from tax_engine.application.ports.parameter_source import ParameterSource
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import (
    Artifact,
    ArtifactCatalog,
    ArtifactKind,
    ArtifactRegistry,
    Money,
)
from tax_engine.domain.capability import Capability, CapabilityRegistry, CapabilityResult
from tax_engine.domain.composition import Composition
from tax_engine.domain.errors import (
    InvalidCompositionError,
    InvalidParameterDataError,
    InvalidRegistrationError,
    InvalidSelectionError,
    NotFoundError,
    UnknownRegistrationError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rounding import NO_ROUNDING
from tax_engine.domain.registry import Namespace
from tax_engine.domain.trace import TraceLine
from tax_engine.domain.worksheet import Worksheet
from tests.manifest_support import required_inputs

D = Decimal
EX_ON = JurisdictionCode("EX-ON")


@dataclass(frozen=True)
class Factor:
    """A made-up parameter: a multiplier."""

    value: Decimal


@dataclass(frozen=True)
class Offset:
    """A made-up parameter: an amount added."""

    value: Decimal


FACTOR = ParameterKind("factor", Factor)
OFFSET = ParameterKind("offset", Offset)

BASE = ArtifactKind("ex/base", Decimal)
SCALED = ArtifactKind("ex/scaled", Decimal)
RESULT = ArtifactKind("ex-on/result", Decimal)
EXTRA = ArtifactKind("ex/extra", Decimal)


@dataclass(frozen=True)
class StepLine(TraceLine):
    """A made-up trace line: which step ran and the value it produced."""

    step: str
    value: Decimal

    @property
    def amount(self) -> Decimal:
        return self.value


class Scale(Capability):
    """Produces `target` = `source` × the `factor` dataset's value."""

    PARAMETERS: ClassVar[Mapping[str, ParameterKind[Any]]] = {"factor": FACTOR}
    CONSUMES: ClassVar[Mapping[str, type]] = {"source": Decimal}
    PRODUCES: ClassVar[Mapping[str, type]] = {"target": Decimal}

    def __init__(self, source: Money, target: Money, factor: ParameterDataset[Factor]) -> None:
        super().__init__(source=source, target=target)
        self._source, self._target, self._factor = source, target, factor

    def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
        value = self._input(inputs, self._source).value * self._factor.values.value
        return CapabilityResult(
            outputs=(Artifact(self._target, value),), trace=(StepLine("scaled", value),)
        )


class Shift(Capability):
    """Produces `target` = `source` + the `offset` dataset's value."""

    PARAMETERS: ClassVar[Mapping[str, ParameterKind[Any]]] = {"offset": OFFSET}
    CONSUMES: ClassVar[Mapping[str, type]] = {"source": Decimal}
    PRODUCES: ClassVar[Mapping[str, type]] = {"target": Decimal}

    def __init__(self, source: Money, target: Money, offset: ParameterDataset[Offset]) -> None:
        super().__init__(source=source, target=target)
        self._source, self._target, self._offset = source, target, offset

    def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
        value = self._input(inputs, self._source).value + self._offset.values.value
        return CapabilityResult(
            outputs=(Artifact(self._target, value),), trace=(StepLine("shifted", value),)
        )


class FakeJurisdictions:
    """An in-memory JurisdictionSource holding the given jurisdictions; records each request."""

    def __init__(self, *jurisdictions: Jurisdiction) -> None:
        self._by_code = {jurisdiction.code: jurisdiction for jurisdiction in jurisdictions}
        self.requests: list[JurisdictionCode] = []

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        self.requests.append(code)
        if code not in self._by_code:
            raise NotFoundError(f"no jurisdiction {code}")
        return self._by_code[code]


class FakeParameters:
    """An in-memory ParameterSource holding datasets by (family, tax year); records each request.

    Like the port's contract asks, a dataset of another kind than the one asked for is an error.
    """

    def __init__(self, *datasets: ParameterDataset[Any]) -> None:
        self._by_key = {(dataset.family, dataset.tax_year): dataset for dataset in datasets}
        self.requests: list[tuple[str, int, ParameterKind[Any]]] = []

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        self.requests.append((family, tax_year, kind))
        if (family, tax_year) not in self._by_key:
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        found: ParameterDataset[Any] = self._by_key[(family, tax_year)]
        if found.kind != kind:
            raise InvalidParameterDataError(
                f"{family} for tax year {tax_year} is a {found.kind.name} dataset, not {kind.name}"
            )
        return found


def dataset[T](
    family: str, kind: ParameterKind[T], values: T, tax_year: int = 2025
) -> ParameterDataset[T]:
    return ParameterDataset(
        family=family,
        tax_year=tax_year,
        kind=kind,
        values=values,
        rounding=NO_ROUNDING,
        sources=(f"https://example.org/{family}",),
    )


def factor_data(tax_year: int = 2025) -> ParameterDataset[Factor]:
    return dataset("ex/factor", FACTOR, Factor(D("3")), tax_year)


def offset_data(tax_year: int = 2025) -> ParameterDataset[Offset]:
    return dataset("ex-on/offset", OFFSET, Offset(D("1")), tax_year)


SCALE = CapabilitySelection(
    name="ex/scale",
    params={"factor": "ex/factor"},
    consumes={"source": "ex/base"},
    produces={"target": "ex/scaled"},
)
SHIFT = CapabilitySelection(
    name="ex/shift",
    params={"offset": "ex-on/offset"},
    consumes={"source": "ex/scaled"},
    produces={"target": "ex-on/result"},
)


def manifest(
    *selections: CapabilitySelection,
    inputs: frozenset[str] = frozenset({"ex/base"}),
    outputs: frozenset[str] = frozenset({"ex-on/result"}),
    version: int = 1,
    valid_from_tax_year: int = 2025,
) -> Manifest:
    return Manifest(
        jurisdiction=EX_ON,
        version=version,
        valid_from_tax_year=valid_from_tax_year,
        inputs=required_inputs(inputs),
        forms=(
            Form(
                required=True,
                name=EX_ON.namespace.identifier("return"),
                instances=None,
                exports=tuple(sorted(outputs)),
                # authored out of order on purpose
                capabilities=selections or (SHIFT, SCALE),
            ),
        ),
    )


def capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register("ex/scale", Scale)
    registry.register("ex/shift", Shift)
    return registry


def artifact_registry() -> ArtifactRegistry:
    registry = ArtifactRegistry()
    for kind in (BASE, SCALED, RESULT, EXTRA):
        registry.register(kind.identifier, kind)
    return registry


def service(
    *manifests: Manifest,
    parameters: ParameterSource | None = None,
    capabilities: CapabilityRegistry | None = None,
    artifacts: ArtifactRegistry | None = None,
) -> TaxComputationService:
    jurisdictions: JurisdictionSource = FakeJurisdictions(
        Jurisdiction(code=EX_ON, manifests=manifests or (manifest(),))
    )
    return TaxComputationService(
        jurisdictions,
        parameters if parameters is not None else FakeParameters(factor_data(), offset_data()),
        capabilities if capabilities is not None else capability_registry(),
        artifacts if artifacts is not None else artifact_registry(),
    )


def test_computes_a_manifest_end_to_end() -> None:
    worksheet = service().compute(EX_ON, 2025, Artifact(BASE, D("5")))["ex-on/return"][0]

    assert_type(worksheet, Worksheet)
    assert worksheet.get(SCALED).value == D("15")
    assert worksheet.get(RESULT).value == D("16")
    assert isinstance(worksheet.producer_of(SCALED), Scale)
    assert isinstance(worksheet.producer_of(RESULT), Shift)
    assert worksheet.producer_of(BASE) is None
    assert worksheet.trace == (StepLine("scaled", D("15")), StepLine("shifted", D("16")))


def test_composes_the_manifests_selections_in_contract_order() -> None:
    composition = service().compose(EX_ON, 2025).form("ex-on/return").composition

    assert_type(composition, Composition)
    assert [type(capability) for capability in composition.order] == [Scale, Shift]
    scale, shift = composition.order
    assert scale.consumes == frozenset({BASE}) and scale.produces == frozenset({SCALED})
    assert shift.consumes == frozenset({SCALED}) and shift.produces == frozenset({RESULT})


def test_compose_is_deterministic() -> None:
    computation = service()

    first = computation.compose(EX_ON, 2025).form("ex-on/return").composition.order
    second = computation.compose(EX_ON, 2025).form("ex-on/return").composition.order

    def shape(order: tuple[Capability, ...]) -> list[tuple[type, frozenset[Any], frozenset[Any]]]:
        return [(type(c), c.consumes, c.produces) for c in order]

    assert shape(first) == shape(second)


def test_the_composition_takes_and_returns_the_manifests_inputs_and_outputs() -> None:
    composition = service().compose(EX_ON, 2025).form("ex-on/return").composition

    with pytest.raises(InvalidCompositionError, match="missing input 'base'"):
        composition.compute()
    with pytest.raises(InvalidCompositionError, match="'scaled' is not an input"):
        composition.compute(Artifact(BASE, D("5")), Artifact(SCALED, D("1")))


def test_compose_returns_the_same_forms_for_the_same_jurisdiction_and_year() -> None:
    jurisdictions = FakeJurisdictions(Jurisdiction(code=EX_ON, manifests=(manifest(),)))
    computation = TaxComputationService(
        jurisdictions,
        FakeParameters(factor_data(), offset_data()),
        capability_registry(),
        artifact_registry(),
    )

    assert computation.compose(EX_ON, 2025) is computation.compose(EX_ON, 2025)
    assert jurisdictions.requests == [EX_ON]


def test_compose_keeps_a_separate_form_set_per_tax_year() -> None:
    parameters = FakeParameters(
        factor_data(2025), offset_data(2025), factor_data(2026), offset_data(2026)
    )
    computation = service(parameters=parameters)

    assert computation.compose(EX_ON, 2025) is not computation.compose(EX_ON, 2026)


def test_compose_keeps_a_separate_form_set_per_jurisdiction() -> None:
    other = JurisdictionCode("EX-AB")
    computation = TaxComputationService(
        FakeJurisdictions(
            Jurisdiction(code=EX_ON, manifests=(manifest(),)),
            Jurisdiction(code=other, manifests=(manifest(),)),
        ),
        FakeParameters(factor_data(), offset_data()),
        capability_registry(),
        artifact_registry(),
    )

    assert computation.compose(EX_ON, 2025) is not computation.compose(other, 2025)


def test_a_failed_compose_is_not_cached() -> None:
    jurisdictions = FakeJurisdictions(Jurisdiction(code=EX_ON, manifests=(manifest(),)))
    computation = TaxComputationService(
        jurisdictions,
        FakeParameters(factor_data()),
        capability_registry(),
        artifact_registry(),
    )

    for _ in range(2):
        with pytest.raises(NotFoundError):
            computation.compose(EX_ON, 2025)

    assert jurisdictions.requests == [EX_ON, EX_ON]


def test_uses_the_manifest_for_the_tax_year_and_that_years_datasets() -> None:
    later = manifest(SCALE, outputs=frozenset({"ex/scaled"}), version=2, valid_from_tax_year=2027)
    parameters = FakeParameters(factor_data(2026), offset_data(2026), factor_data(2027))

    computation = service(manifest(), later, parameters=parameters)

    assert [
        type(c) for c in computation.compose(EX_ON, 2026).form("ex-on/return").composition.order
    ] == [Scale, Shift]
    assert [
        type(c) for c in computation.compose(EX_ON, 2027).form("ex-on/return").composition.order
    ] == [Scale]
    assert ("ex/factor", 2026, FACTOR) in parameters.requests
    assert ("ex-on/offset", 2026, OFFSET) in parameters.requests
    assert all(year != 2025 for _family, year, _kind in parameters.requests)


def test_asks_for_each_dataset_with_its_slots_kind() -> None:
    parameters = FakeParameters(factor_data(), offset_data())

    service(parameters=parameters).compose(EX_ON, 2025)

    assert sorted(parameters.requests, key=lambda request: request[0]) == [
        ("ex-on/offset", 2025, OFFSET),
        ("ex/factor", 2025, FACTOR),
    ]


def test_resolves_through_the_registries_it_was_given_not_the_shared_ones() -> None:
    assert "ex/scale" not in CapabilityRegistry.shared().identifiers()
    assert "ex/base" not in ArtifactRegistry.shared().identifiers()

    assert len(service().compose(EX_ON, 2025).form("ex-on/return").composition.order) == 2


def test_an_unknown_jurisdiction_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="EX-ZZ"):
        service().compose(JurisdictionCode("EX-ZZ"), 2025)


def test_a_tax_year_before_every_manifest_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="2024"):
        service().compose(EX_ON, 2024)


def test_an_unknown_capability_name_is_an_unknown_registration() -> None:
    unknown = CapabilitySelection(
        name="ex/nowhere",
        params={},
        consumes={"source": "ex/base"},
        produces={"target": "ex/scaled"},
    )

    with pytest.raises(UnknownRegistrationError, match="'ex/nowhere'"):
        service(manifest(unknown, SHIFT)).compose(EX_ON, 2025)


@pytest.mark.parametrize(
    "selections",
    [
        pytest.param(
            (
                CapabilitySelection(
                    name="ex/scale",
                    params={"factor": "ex/factor"},
                    consumes={"source": "ex/nowhere"},
                    produces={"target": "ex/scaled"},
                ),
                SHIFT,
            ),
            id="consumed",
        ),
        pytest.param(
            (
                SCALE,
                CapabilitySelection(
                    name="ex/shift",
                    params={"offset": "ex-on/offset"},
                    consumes={"source": "ex/scaled"},
                    produces={"target": "ex/nowhere"},
                ),
            ),
            id="produced",
        ),
    ],
)
def test_an_unknown_artifact_identifier_in_a_selection_is_an_unknown_registration(
    selections: tuple[CapabilitySelection, ...],
) -> None:
    with pytest.raises(UnknownRegistrationError, match="'ex/nowhere'"):
        service(manifest(*selections)).compose(EX_ON, 2025)


@pytest.mark.parametrize(
    ("inputs", "outputs"),
    [
        pytest.param(frozenset({"ex/nowhere"}), frozenset({"ex-on/result"}), id="input"),
        pytest.param(frozenset({"ex/base"}), frozenset({"ex/nowhere"}), id="output"),
    ],
)
def test_an_unknown_input_or_output_identifier_is_an_unknown_registration(
    inputs: frozenset[str], outputs: frozenset[str]
) -> None:
    with pytest.raises(UnknownRegistrationError, match="'ex/nowhere'"):
        service(manifest(inputs=inputs, outputs=outputs)).compose(EX_ON, 2025)


def test_a_missing_dataset_is_not_found() -> None:
    parameters = FakeParameters(factor_data())

    with pytest.raises(NotFoundError, match="ex-on/offset"):
        service(parameters=parameters).compose(EX_ON, 2025)


def test_a_dataset_of_the_wrong_kind_is_the_parameter_sources_error() -> None:
    wrong = dataset("ex/factor", OFFSET, Offset(D("3")))
    parameters = FakeParameters(wrong, offset_data())

    with pytest.raises(InvalidParameterDataError, match="ex/factor"):
        service(parameters=parameters).compose(EX_ON, 2025)


@pytest.mark.parametrize(
    ("params", "slot"),
    [
        pytest.param({"factor": "ex/factor", "bonus": "ex/bonus"}, "bonus", id="undeclared-key"),
        pytest.param({"factor": "ex/factor", "source": "ex/base"}, "source", id="artifact-slot"),
    ],
)
def test_a_params_key_that_is_not_a_parameter_slot_is_an_invalid_selection(
    params: dict[str, str], slot: str
) -> None:
    misfilled = CapabilitySelection(
        name="ex/scale",
        params=params,
        consumes={"source": "ex/base"},
        produces={"target": "ex/scaled"},
    )
    parameters = FakeParameters(factor_data(), offset_data())

    with pytest.raises(InvalidSelectionError, match=repr(slot)):
        service(manifest(misfilled, SHIFT), parameters=parameters).compose(EX_ON, 2025)
    assert all(family != params[slot] for family, _year, _kind in parameters.requests)


def test_a_selection_filling_the_wrong_slots_is_an_invalid_selection() -> None:
    misfilled = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"input": "ex/base"},
        produces={"target": "ex/scaled"},
    )

    with pytest.raises(InvalidSelectionError, match="'input'"):
        service(manifest(misfilled, SHIFT)).compose(EX_ON, 2025)


@pytest.mark.parametrize(
    ("inputs", "outputs", "message"),
    [
        pytest.param(
            frozenset({"ex/base", "ex/scaled"}),
            frozenset({"ex-on/result"}),
            "input 'scaled' is also produced by Scale",
            id="input-also-produced",
        ),
        pytest.param(
            frozenset({"ex/base", "ex/scaled"}),
            frozenset({"ex-on/result", "ex/scaled"}),
            "input 'scaled' is also produced by Scale",
            id="input-also-produced-and-declared-output",
        ),
        pytest.param(
            frozenset({"ex/base"}),
            frozenset({"ex/scaled"}),
            "orphan output 'result'",
            id="undeclared-output",
        ),
        pytest.param(
            frozenset({"ex/base", "ex/extra"}),
            frozenset({"ex-on/result"}),
            "input 'extra' is consumed by nothing",
            id="unused-input",
        ),
        pytest.param(
            frozenset({"ex/base"}),
            frozenset({"ex-on/result", "ex/extra"}),
            "declared output 'extra' is produced by nothing",
            id="unproduced-output",
        ),
        pytest.param(
            frozenset({"ex/base", "ex/extra"}),
            frozenset({"ex-on/result", "ex/scaled"}),
            "input 'extra' is consumed by nothing",
            id="unused-input-another-kind-is-the-output",
        ),
    ],
)
def test_inputs_or_outputs_the_composition_rejects_are_an_invalid_composition(
    inputs: frozenset[str], outputs: frozenset[str], message: str
) -> None:
    with pytest.raises(InvalidCompositionError, match=message):
        service(manifest(inputs=inputs, outputs=outputs)).compose(EX_ON, 2025)


def test_an_identifier_registered_as_something_other_than_a_kind_is_an_invalid_registration() -> (
    None
):
    artifacts = artifact_registry()
    artifacts.register("ex/stray", object())

    with pytest.raises(InvalidRegistrationError, match="'ex/stray'.*not as an artifact kind"):
        service(
            manifest(outputs=frozenset({"ex-on/result", "ex/stray"})), artifacts=artifacts
        ).compose(EX_ON, 2025)


def test_an_identifier_in_a_selection_registered_as_something_other_than_a_kind_is_invalid() -> (
    None
):
    artifacts = artifact_registry()
    artifacts.register("ex/stray", object())
    stray = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/stray"},
        produces={"target": "ex/scaled"},
    )

    with pytest.raises(InvalidRegistrationError, match="'ex/stray'.*not as an artifact kind"):
        service(manifest(stray, SHIFT), artifacts=artifacts).compose(EX_ON, 2025)


# --- list slots: a consumed slot filled with a list of identifiers ------------------------------
#
# The list-slot class is defined inside a cached factory, so a class definition the base rejects
# fails the tests that use it rather than the collection of this whole module.

PART_ONE = ArtifactKind("ex/part_one", Decimal)
PART_TWO = ArtifactKind("ex/part_two", Decimal)
PART_THREE = ArtifactKind("ex/part_three", Decimal)


@dataclass(frozen=True)
class PartsLine(TraceLine):
    """A made-up trace line: the identifiers of the parts added, in order, and their total."""

    parts: tuple[str, ...]
    total: Decimal

    @property
    def amount(self) -> Decimal:
        return self.total


@cache
def total_class() -> Any:
    class Total(Capability):
        """Produces `total` = the sum of its `parts`, each read with `_input`, in their order."""

        CONSUMES = {"parts": list[Decimal]}
        PRODUCES = {"total": Decimal}

        def __init__(self, parts: tuple[Money, ...], total: Money) -> None:
            super().__init__(parts=parts, total=total)
            self.parts, self.total = parts, total

        def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
            values = [self._input(inputs, kind).value for kind in self.parts]
            value = sum(values, D(0))
            line = PartsLine(tuple(kind.identifier for kind in self.parts), value)
            return CapabilityResult(outputs=(Artifact(self.total, value),), trace=(line,))

    return Total


def list_slot_manifest(parts: Any, *producers: CapabilitySelection) -> Manifest:
    """Three made-up producers of parts and a Total over `parts` producing `ex-on/result`."""
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_one"},
    )
    to_two = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_two"},
    )
    to_three = CapabilitySelection(  # chained after to_one, so the total waits for a chain
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/part_one"},
        produces={"target": "ex/part_three"},
    )
    total = CapabilitySelection(
        name="ex/total_up",
        params={},
        consumes={"parts": parts},
        produces={"total": "ex-on/result"},
    )
    return manifest(total, *(producers or (to_three, to_two, to_one)))


def list_slot_service(*manifests: Manifest) -> TaxComputationService:
    capabilities = capability_registry()
    capabilities.register("ex/total_up", total_class())
    artifacts = artifact_registry()
    for kind in (PART_ONE, PART_TWO, PART_THREE):
        artifacts.register(kind.identifier, kind)
    return service(*manifests, capabilities=capabilities, artifacts=artifacts)


def test_a_list_slot_receives_its_kinds_in_manifest_order() -> None:
    parts = ("ex/part_two", "ex/part_three", "ex/part_one")
    total_cls = total_class()

    composition = (
        list_slot_service(list_slot_manifest(parts))
        .compose(EX_ON, 2025)
        .form("ex-on/return")
        .composition
    )

    total = composition.order[-1]
    assert isinstance(total, total_cls)
    assert total.parts == (PART_TWO, PART_THREE, PART_ONE)
    assert total.consumes == frozenset({PART_ONE, PART_TWO, PART_THREE})
    assert total.produces == frozenset({RESULT})


def test_the_list_slot_capability_runs_after_all_three_producers() -> None:
    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    composition = (
        list_slot_service(list_slot_manifest(parts))
        .compose(EX_ON, 2025)
        .form("ex-on/return")
        .composition
    )

    assert [type(capability) for capability in composition.order] == [
        Scale,
        Shift,
        Shift,
        total_class(),
    ]


def test_computes_a_list_slot_end_to_end() -> None:
    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    worksheet = list_slot_service(list_slot_manifest(parts)).compute(
        EX_ON, 2025, Artifact(BASE, D("5"))
    )["ex-on/return"][0]

    # part_one = 5 × 3 = 15; part_two = 5 + 1 = 6; part_three = 15 + 1 = 16.
    assert worksheet.get(PART_ONE).value == D("15")
    assert worksheet.get(PART_TWO).value == D("6")
    assert worksheet.get(PART_THREE).value == D("16")
    assert worksheet.get(RESULT).value == D("37")
    assert isinstance(worksheet.producer_of(RESULT), total_class())
    assert worksheet.trace[-1] == PartsLine(parts, D("37"))


def test_an_unknown_identifier_in_a_list_is_an_unknown_registration() -> None:
    parts = ("ex/part_two", "ex/nowhere", "ex/part_one")

    with pytest.raises(UnknownRegistrationError, match="'ex/nowhere'"):
        list_slot_service(list_slot_manifest(parts)).compose(EX_ON, 2025)


def test_a_listed_kind_nothing_produces_is_an_invalid_composition() -> None:
    parts = ("ex/part_two", "ex/extra", "ex/part_one")

    with pytest.raises(InvalidCompositionError, match="no producer for 'extra'"):
        list_slot_service(list_slot_manifest(parts)).compose(EX_ON, 2025)


def test_a_kind_listed_twice_is_an_invalid_selection() -> None:
    parts = ("ex/part_two", "ex/part_three", "ex/part_one", "ex/part_two")

    with pytest.raises(InvalidSelectionError, match="'parts'"):
        list_slot_service(list_slot_manifest(parts)).compose(EX_ON, 2025)


def test_a_single_identifier_for_a_list_slot_is_an_invalid_selection() -> None:
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_one"},
    )

    with pytest.raises(InvalidSelectionError, match="'parts'"):
        list_slot_service(list_slot_manifest("ex/part_one", to_one)).compose(EX_ON, 2025)


def test_a_list_for_a_single_slot_is_an_invalid_selection() -> None:
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": ("ex/base",)},
        produces={"target": "ex/part_one"},
    )

    with pytest.raises(InvalidSelectionError, match="'source'"):
        list_slot_service(list_slot_manifest(("ex/part_one",), to_one)).compose(EX_ON, 2025)


# --- core/sum: the generic sum over a list slot, wired by a made-up manifest -------------------
#
# `Sum` is imported inside a cached factory, so its absence fails the tests that use it rather
# than the collection of this whole module. It is registered in a private registry under its
# shared identifier, `core/sum`.


@cache
def sum_class() -> Any:
    from tax_engine.domain.capabilities.sum import Sum

    return Sum


def sum_manifest(parts: tuple[str, ...]) -> Manifest:
    """The three made-up producers of parts and `core/sum` over `parts` producing `ex-on/result`."""
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_one"},
    )
    to_two = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_two"},
    )
    to_three = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/part_one"},
        produces={"target": "ex/part_three"},
    )
    total = CapabilitySelection(
        name="core/sum",
        params={},
        consumes={"parts": parts},
        produces={"output": "ex-on/result"},
    )
    return manifest(total, to_three, to_two, to_one)


def sum_service(*manifests: Manifest) -> TaxComputationService:
    capabilities = capability_registry()
    capabilities.register("core/sum", sum_class())
    artifacts = artifact_registry()
    for kind in (PART_ONE, PART_TWO, PART_THREE):
        artifacts.register(kind.identifier, kind)
    return service(*manifests, capabilities=capabilities, artifacts=artifacts)


def test_computes_core_sum_end_to_end() -> None:
    from tax_engine.domain.trace import SumLine

    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    worksheet = sum_service(sum_manifest(parts)).compute(EX_ON, 2025, Artifact(BASE, D("5")))[
        "ex-on/return"
    ][0]

    # part_one = 5 × 3 = 15; part_two = 5 + 1 = 6; part_three = 15 + 1 = 16.
    assert worksheet.get(RESULT).value == D("37")
    assert isinstance(worksheet.producer_of(RESULT), sum_class())
    assert worksheet.trace[-1] == SumLine(
        RESULT, ((PART_TWO, D("6")), (PART_THREE, D("16")), (PART_ONE, D("15"))), D("37")
    )
    assert [type(line) for line in worksheet.trace].count(SumLine) == 1


def test_core_sum_runs_after_all_its_parts() -> None:
    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    composition = (
        sum_service(sum_manifest(parts)).compose(EX_ON, 2025).form("ex-on/return").composition
    )

    assert type(composition.order[-1]) is sum_class()
    assert composition.order[-1].consumes == frozenset({PART_ONE, PART_TWO, PART_THREE})


# --- core/sum_not_below_zero: the sum over a list slot, floored at zero, by a made-up manifest -
#
# Like `Sum` above, `SumNotBelowZero` is imported inside a cached factory so its absence fails
# only the tests that use it, and is registered in a private registry under its shared
# identifier, `core/sum_not_below_zero`. It reuses `sum_manifest`'s three made-up producers of
# parts (part_one = base × 3, part_two = base + 1, part_three = part_one + 1).


@cache
def sum_not_below_zero_class() -> Any:
    from tax_engine.domain.capabilities.sum_not_below_zero import SumNotBelowZero

    return SumNotBelowZero


def sum_not_below_zero_service(parts: tuple[str, ...]) -> TaxComputationService:
    """The three producers of parts and `core/sum_not_below_zero` producing `ex-on/result`."""
    base = sum_manifest(parts)
    total = CapabilitySelection(
        name="core/sum_not_below_zero",
        params={},
        consumes={"parts": parts},
        produces={"output": "ex-on/result"},
    )
    built = manifest(total, *(c for c in base.forms[0].capabilities if c.name != "core/sum"))
    capabilities = capability_registry()
    capabilities.register("core/sum_not_below_zero", sum_not_below_zero_class())
    artifacts = artifact_registry()
    for kind in (PART_ONE, PART_TWO, PART_THREE):
        artifacts.register(kind.identifier, kind)
    return service(built, capabilities=capabilities, artifacts=artifacts)


def test_computes_core_sum_not_below_zero_end_to_end() -> None:
    from tax_engine.domain.trace import SumNotBelowZeroLine

    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    worksheet = sum_not_below_zero_service(parts).compute(EX_ON, 2025, Artifact(BASE, D("5")))[
        "ex-on/return"
    ][0]

    # part_one = 5 × 3 = 15; part_two = 5 + 1 = 6; part_three = 15 + 1 = 16; 37 is above zero.
    assert worksheet.get(RESULT).value == D("37")
    assert isinstance(worksheet.producer_of(RESULT), sum_not_below_zero_class())
    assert worksheet.trace[-1] == SumNotBelowZeroLine(
        RESULT, ((PART_TWO, D("6")), (PART_THREE, D("16")), (PART_ONE, D("15"))), D("37")
    )
    assert [type(line) for line in worksheet.trace].count(SumNotBelowZeroLine) == 1


def test_core_sum_not_below_zero_floors_a_negative_total_end_to_end() -> None:
    from tax_engine.domain.trace import SumNotBelowZeroLine

    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    worksheet = sum_not_below_zero_service(parts).compute(EX_ON, 2025, Artifact(BASE, D("-20")))[
        "ex-on/return"
    ][0]

    # part_one = −60; part_two = −19; part_three = −59; the sum, −138, is floored: result = 0.
    assert worksheet.get(RESULT).value == D("0")
    assert str(worksheet.get(RESULT).value) == "0"
    assert worksheet.trace[-1] == SumNotBelowZeroLine(
        RESULT, ((PART_TWO, D("-19")), (PART_THREE, D("-59")), (PART_ONE, D("-60"))), D("0")
    )
    assert [type(line) for line in worksheet.trace].count(SumNotBelowZeroLine) == 1


def test_core_sum_not_below_zero_runs_after_all_its_parts() -> None:
    parts = ("ex/part_two", "ex/part_three", "ex/part_one")

    composition = (
        sum_not_below_zero_service(parts).compose(EX_ON, 2025).form("ex-on/return").composition
    )

    assert type(composition.order[-1]) is sum_not_below_zero_class()
    assert composition.order[-1].consumes == frozenset({PART_ONE, PART_TWO, PART_THREE})


def test_core_sum_not_below_zero_refuses_a_single_kind_for_its_parts_at_wiring() -> None:
    selection = CapabilitySelection(
        name="core/sum_not_below_zero",
        params={},
        consumes={"parts": "ex/part_one"},
        produces={"output": "ex-on/result"},
    )
    capabilities = capability_registry()
    capabilities.register("core/sum_not_below_zero", sum_not_below_zero_class())
    wired = service(manifest(selection, SCALE), capabilities=capabilities)

    with pytest.raises(InvalidSelectionError, match="'parts'"):
        wired.compose(EX_ON, 2025)


# --- core/apply_rate: base × a rate dataset's rate, wired by a made-up manifest ----------------
#
# `ApplyRate` is imported inside a cached factory, like `Sum` above, so its absence fails only
# the tests that use it. It is registered in a private registry under its shared identifier,
# `core/apply_rate`, and reads a made-up `rate` dataset that rounds half-up to the cent.


@cache
def apply_rate_class() -> Any:
    from tax_engine.domain.capabilities.apply_rate import ApplyRate

    return ApplyRate


def portion_rate_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.rate import RATE, Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/portion_rate",
        tax_year=tax_year,
        kind=RATE,
        values=Rate(D("0.5")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/portion_rate",),
    )


APPLY_RATE = CapabilitySelection(
    name="core/apply_rate",
    params={"rate": "ex/portion_rate"},
    consumes={"base": "ex/scaled"},
    produces={"output": "ex-on/result"},
)


def apply_rate_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/apply_rate", apply_rate_class())
    parameters = FakeParameters(factor_data(), offset_data(), portion_rate_data())
    built = service(
        manifest(APPLY_RATE, SCALE),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_apply_rate_end_to_end() -> None:
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import RateAppliedLine

    built, _parameters = apply_rate_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5.01")))["ex-on/return"][0]

    # scaled = 5.01 × 3 = 15.03; result = 15.03 × 0.5 = 7.515, rounded half-up to 7.52.
    assert worksheet.get(SCALED).value == D("15.03")
    assert worksheet.get(RESULT).value == D("7.52")
    assert isinstance(worksheet.producer_of(RESULT), apply_rate_class())
    assert worksheet.trace[-1] == RateAppliedLine(
        RESULT,
        SCALED,
        D("15.03"),
        Rate(D("0.5")),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("7.52"),
    )
    assert [type(line) for line in worksheet.trace].count(RateAppliedLine) == 1


def test_core_apply_rate_runs_after_its_base_is_produced() -> None:
    built, _parameters = apply_rate_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is apply_rate_class()
    assert composition.order[-1].consumes == frozenset({SCALED})


def test_core_apply_rate_asks_for_its_dataset_as_a_rate() -> None:
    from tax_engine.domain.parameters.rate import RATE

    built, parameters = apply_rate_service()

    built.compose(EX_ON, 2025)

    assert ("ex/portion_rate", 2025, RATE) in parameters.requests


# --- core/subtract: amount less another artifact, wired by a made-up manifest -----------------
#
# `Subtract` is imported inside a cached factory, like `Sum` above, so its absence fails only the
# tests that use it. It is registered in a private registry under its shared identifier,
# `core/subtract`, and takes one of the manifest's inputs and one produced artifact.


@cache
def subtract_class() -> Any:
    from tax_engine.domain.capabilities.subtract import Subtract

    return Subtract


def subtract_service(amount: str, less: str) -> TaxComputationService:
    """`ex/scale` (base × 3) and `core/subtract` producing `ex-on/result` = amount − less."""
    subtract = CapabilitySelection(
        name="core/subtract",
        params={},
        consumes={"amount": amount, "less": less},
        produces={"output": "ex-on/result"},
    )
    capabilities = capability_registry()
    capabilities.register("core/subtract", subtract_class())
    return service(manifest(subtract, SCALE), capabilities=capabilities)  # out of order on purpose


def test_computes_core_subtract_end_to_end() -> None:
    from tax_engine.domain.trace import SubtractedLine

    worksheet = subtract_service("ex/scaled", "ex/base").compute(
        EX_ON, 2025, Artifact(BASE, D("5.01"))
    )["ex-on/return"][0]

    # scaled = 5.01 × 3 = 15.03; result = 15.03 − 5.01 = 10.02.
    assert worksheet.get(RESULT).value == D("10.02")
    assert isinstance(worksheet.producer_of(RESULT), subtract_class())
    assert worksheet.trace[-1] == SubtractedLine(
        RESULT, SCALED, D("15.03"), BASE, D("5.01"), D("10.02")
    )
    assert [type(line) for line in worksheet.trace].count(SubtractedLine) == 1


def test_core_subtract_produces_a_negative_result_end_to_end() -> None:
    from tax_engine.domain.trace import SubtractedLine

    worksheet = subtract_service("ex/base", "ex/scaled").compute(
        EX_ON, 2025, Artifact(BASE, D("5.01"))
    )["ex-on/return"][0]

    # result = 5.01 − 15.03 = −10.02, not floored at zero.
    assert worksheet.get(RESULT).value == D("-10.02")
    assert worksheet.trace[-1] == SubtractedLine(
        RESULT, BASE, D("5.01"), SCALED, D("15.03"), D("-10.02")
    )


def test_core_subtract_runs_after_what_it_consumes_is_produced() -> None:
    composition = (
        subtract_service("ex/scaled", "ex/base")
        .compose(EX_ON, 2025)
        .form("ex-on/return")
        .composition
    )

    assert type(composition.order[-1]) is subtract_class()
    assert composition.order[-1].consumes == frozenset({SCALED, BASE})


# --- core/subtract_not_below_zero: amount less another, floored at zero, by a made-up manifest -
#
# Like `Subtract` above, `SubtractNotBelowZero` is imported inside a cached factory so its absence
# fails only the tests that use it, and is registered in a private registry under its shared
# identifier, `core/subtract_not_below_zero`.


@cache
def subtract_not_below_zero_class() -> Any:
    from tax_engine.domain.capabilities.subtract_not_below_zero import SubtractNotBelowZero

    return SubtractNotBelowZero


def subtract_not_below_zero_service(amount: str, less: str) -> TaxComputationService:
    """`ex/scale` (base × 3) and `core/subtract_not_below_zero` producing `ex-on/result`."""
    subtract = CapabilitySelection(
        name="core/subtract_not_below_zero",
        params={},
        consumes={"amount": amount, "less": less},
        produces={"output": "ex-on/result"},
    )
    capabilities = capability_registry()
    capabilities.register("core/subtract_not_below_zero", subtract_not_below_zero_class())
    return service(manifest(subtract, SCALE), capabilities=capabilities)  # out of order on purpose


def test_computes_core_subtract_not_below_zero_end_to_end() -> None:
    from tax_engine.domain.trace import SubtractedNotBelowZeroLine

    worksheet = subtract_not_below_zero_service("ex/scaled", "ex/base").compute(
        EX_ON, 2025, Artifact(BASE, D("5.01"))
    )["ex-on/return"][0]

    # scaled = 5.01 × 3 = 15.03; result = 15.03 − 5.01 = 10.02, above zero so unchanged.
    assert worksheet.get(RESULT).value == D("10.02")
    assert isinstance(worksheet.producer_of(RESULT), subtract_not_below_zero_class())
    assert worksheet.trace[-1] == SubtractedNotBelowZeroLine(
        RESULT, SCALED, D("15.03"), BASE, D("5.01"), D("10.02")
    )
    assert [type(line) for line in worksheet.trace].count(SubtractedNotBelowZeroLine) == 1


def test_core_subtract_not_below_zero_floors_a_negative_difference_end_to_end() -> None:
    from tax_engine.domain.trace import SubtractedNotBelowZeroLine

    worksheet = subtract_not_below_zero_service("ex/base", "ex/scaled").compute(
        EX_ON, 2025, Artifact(BASE, D("5.01"))
    )["ex-on/return"][0]

    # 5.01 − 15.03 = −10.02, floored: result = 0.
    assert worksheet.get(RESULT).value == D("0")
    assert worksheet.trace[-1] == SubtractedNotBelowZeroLine(
        RESULT, BASE, D("5.01"), SCALED, D("15.03"), D("0")
    )
    assert [type(line) for line in worksheet.trace].count(SubtractedNotBelowZeroLine) == 1


def test_core_subtract_not_below_zero_runs_after_what_it_consumes_is_produced() -> None:
    composition = (
        subtract_not_below_zero_service("ex/scaled", "ex/base")
        .compose(EX_ON, 2025)
        .form("ex-on/return")
        .composition
    )

    assert type(composition.order[-1]) is subtract_not_below_zero_class()
    assert composition.order[-1].consumes == frozenset({SCALED, BASE})


# --- core/credit_amount: a credit dataset's amount as a part of core/sum, by a made-up manifest -
#
# `CreditAmount` is imported inside a cached factory, like `Sum` above, so its absence fails only
# the tests that use it. It is registered in a private registry under its shared identifier,
# `core/credit_amount`; its selection fills no consumed slot, and it reads a made-up `credit`
# dataset that rounds half-up to the cent.


@cache
def credit_amount_class() -> Any:
    from tax_engine.domain.capabilities.credit_amount import CreditAmount

    return CreditAmount


def personal_credit_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.credit import CREDIT, Credit
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/personal_credit",
        tax_year=tax_year,
        kind=CREDIT,
        values=Credit(D("1000.005")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/personal_credit",),
    )


CREDIT_AMOUNT = CapabilitySelection(
    name="core/credit_amount",
    params={"amount": "ex/personal_credit"},
    consumes={},
    produces={"output": "ex/part_two"},
)


def credit_amount_service() -> tuple[TaxComputationService, FakeParameters]:
    """`ex/scale` (base × 3) and `core/credit_amount` summed by `core/sum` into `ex-on/result`."""
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_one"},
    )
    total = CapabilitySelection(
        name="core/sum",
        params={},
        consumes={"parts": ("ex/part_one", "ex/part_two")},
        produces={"output": "ex-on/result"},
    )
    capabilities = capability_registry()
    capabilities.register("core/sum", sum_class())
    capabilities.register("core/credit_amount", credit_amount_class())
    artifacts = artifact_registry()
    for kind in (PART_ONE, PART_TWO):
        artifacts.register(kind.identifier, kind)
    parameters = FakeParameters(factor_data(), offset_data(), personal_credit_data())
    built = service(
        manifest(total, CREDIT_AMOUNT, to_one),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
        artifacts=artifacts,
    )
    return built, parameters


def test_computes_core_credit_amount_as_a_part_of_core_sum_end_to_end() -> None:
    from tax_engine.domain.parameters.credit import Credit
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import CreditAmountLine, SumLine

    built, _parameters = credit_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5")))["ex-on/return"][0]

    # part_one = 5 × 3 = 15; part_two = 1000.005, rounded half-up to 1000.01; result = 1015.01.
    assert worksheet.get(PART_TWO).value == D("1000.01")
    assert isinstance(worksheet.producer_of(PART_TWO), credit_amount_class())
    assert worksheet.get(RESULT).value == D("1015.01")
    assert (
        CreditAmountLine(
            PART_TWO, Credit(D("1000.005")), RoundTo(D("0.01"), RoundingMode.HALF_UP), D("1000.01")
        )
        in worksheet.trace
    )
    assert [type(line) for line in worksheet.trace].count(CreditAmountLine) == 1
    assert worksheet.trace[-1] == SumLine(
        RESULT, ((PART_ONE, D("15")), (PART_TWO, D("1000.01"))), D("1015.01")
    )


def test_the_composition_accepts_a_selection_without_consumes() -> None:
    built, _parameters = credit_amount_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    (credit,) = [c for c in composition.order if type(c) is credit_amount_class()]
    assert credit.consumes == frozenset()
    assert credit.produces == frozenset({PART_TWO})
    assert type(composition.order[-1]) is sum_class()


def test_core_credit_amount_asks_for_its_dataset_as_a_credit() -> None:
    from tax_engine.domain.parameters.credit import CREDIT

    built, parameters = credit_amount_service()

    built.compose(EX_ON, 2025)

    assert ("ex/personal_credit", 2025, CREDIT) in parameters.requests


# --- core/capped_amount: the lesser of base and an amount dataset's cap, by a made-up manifest --
#
# `CappedAmount` is imported inside a cached factory, like `Sum` above, so its absence fails only
# the tests that use it. It is registered in a private registry under its shared identifier,
# `core/capped_amount`, and reads a made-up `amount` dataset that rounds half-up to the cent.


@cache
def capped_amount_class() -> Any:
    from tax_engine.domain.capabilities.capped_amount import CappedAmount

    return CappedAmount


def some_cap_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.amount import AMOUNT, Amount
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/some_cap",
        tax_year=tax_year,
        kind=AMOUNT,
        values=Amount(D("20")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/some_cap",),
    )


CAPPED_AMOUNT = CapabilitySelection(
    name="core/capped_amount",
    params={"cap": "ex/some_cap"},
    consumes={"base": "ex/scaled"},
    produces={"output": "ex-on/result"},
)


def capped_amount_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/capped_amount", capped_amount_class())
    parameters = FakeParameters(factor_data(), offset_data(), some_cap_data())
    built = service(
        manifest(CAPPED_AMOUNT, SCALE),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_capped_amount_below_the_cap_end_to_end() -> None:
    from tax_engine.domain.parameters.amount import Amount
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import CappedAmountLine

    built, _parameters = capped_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5.005")))["ex-on/return"][0]

    # scaled = 5.005 × 3 = 15.015; below the cap of 20, rounded half-up: result = 15.02.
    assert worksheet.get(SCALED).value == D("15.015")
    assert worksheet.get(RESULT).value == D("15.02")
    assert isinstance(worksheet.producer_of(RESULT), capped_amount_class())
    assert worksheet.trace[-1] == CappedAmountLine(
        RESULT,
        SCALED,
        D("15.015"),
        Amount(D("20")),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("15.02"),
    )
    assert [type(line) for line in worksheet.trace].count(CappedAmountLine) == 1


def test_computes_core_capped_amount_above_the_cap_end_to_end() -> None:
    from tax_engine.domain.parameters.amount import Amount
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import CappedAmountLine

    built, _parameters = capped_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("10")))["ex-on/return"][0]

    # scaled = 10 × 3 = 30; above the cap: result = 20, rounded half-up to 20.00.
    assert worksheet.get(RESULT).value == D("20")
    assert str(worksheet.get(RESULT).value) == "20.00"
    assert worksheet.trace[-1] == CappedAmountLine(
        RESULT,
        SCALED,
        D("30"),
        Amount(D("20")),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("20.00"),
    )


def test_core_capped_amount_runs_after_its_base_is_produced() -> None:
    built, _parameters = capped_amount_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is capped_amount_class()
    assert composition.order[-1].consumes == frozenset({SCALED})


def test_core_capped_amount_asks_for_its_dataset_as_an_amount() -> None:
    from tax_engine.domain.parameters.amount import AMOUNT

    built, parameters = capped_amount_service()

    built.compose(EX_ON, 2025)

    assert ("ex/some_cap", 2025, AMOUNT) in parameters.requests


# --- core/lesser_of: the least of a list of amounts, wired by a made-up manifest ---------------
#
# `LesserOf` is imported inside a cached factory, like `Sum` above, so its absence fails only the
# tests that use it. It is registered in a private registry under its shared identifier,
# `core/lesser_of`, and reads the parts the made-up producers of the list-slot section make.


@cache
def lesser_of_class() -> Any:
    from tax_engine.domain.capabilities.lesser_of import LesserOf

    return LesserOf


def lesser_of_manifest(amounts: tuple[str, ...]) -> Manifest:
    """The made-up producers of the wired parts and `core/lesser_of` over `amounts`.

    Only producers whose part is wired are selected (part three is made from part one), so the
    composition has no orphan output.
    """
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_one"},
    )
    to_two = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_two"},
    )
    to_three = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/part_one"},
        produces={"target": "ex/part_three"},
    )
    lesser = CapabilitySelection(
        name="core/lesser_of",
        params={},
        consumes={"amounts": amounts},
        produces={"output": "ex-on/result"},
    )
    producers = {"ex/part_one": to_one, "ex/part_two": to_two, "ex/part_three": to_three}
    wired = set(amounts) | ({"ex/part_one"} if "ex/part_three" in amounts else set())
    selected = [selection for part, selection in producers.items() if part in wired]
    return manifest(lesser, *reversed(selected))


def lesser_of_service(*manifests: Manifest) -> TaxComputationService:
    capabilities = capability_registry()
    capabilities.register("core/lesser_of", lesser_of_class())
    artifacts = artifact_registry()
    for kind in (PART_ONE, PART_TWO, PART_THREE):
        artifacts.register(kind.identifier, kind)
    return service(*manifests, capabilities=capabilities, artifacts=artifacts)


def test_computes_core_lesser_of_three_amounts_end_to_end() -> None:
    from tax_engine.domain.trace import LesserOfLine

    amounts = ("ex/part_three", "ex/part_two", "ex/part_one")

    worksheet = lesser_of_service(lesser_of_manifest(amounts)).compute(
        EX_ON, 2025, Artifact(BASE, D("5"))
    )["ex-on/return"][0]

    # part_one = 5 × 3 = 15; part_two = 5 + 1 = 6; part_three = 15 + 1 = 16; the least is 6.
    assert worksheet.get(RESULT).value == D("6")
    assert isinstance(worksheet.producer_of(RESULT), lesser_of_class())
    assert worksheet.trace[-1] == LesserOfLine(
        RESULT, ((PART_THREE, D("16")), (PART_TWO, D("6")), (PART_ONE, D("15"))), D("6")
    )
    assert [type(line) for line in worksheet.trace].count(LesserOfLine) == 1


def test_computes_core_lesser_of_two_amounts_end_to_end() -> None:
    from tax_engine.domain.trace import LesserOfLine

    amounts = ("ex/part_three", "ex/part_one")

    worksheet = lesser_of_service(lesser_of_manifest(amounts)).compute(
        EX_ON, 2025, Artifact(BASE, D("5"))
    )["ex-on/return"][0]

    # part_one = 15 and part_three = 16: the lesser is part_one's 15.
    assert worksheet.get(RESULT).value == D("15")
    assert worksheet.trace[-1] == LesserOfLine(
        RESULT, ((PART_THREE, D("16")), (PART_ONE, D("15"))), D("15")
    )


def test_core_lesser_of_runs_after_all_its_amounts() -> None:
    amounts = ("ex/part_three", "ex/part_two", "ex/part_one")

    composition = (
        lesser_of_service(lesser_of_manifest(amounts))
        .compose(EX_ON, 2025)
        .form("ex-on/return")
        .composition
    )

    assert type(composition.order[-1]) is lesser_of_class()
    assert composition.order[-1].consumes == frozenset({PART_ONE, PART_TWO, PART_THREE})


def test_core_lesser_of_with_no_amounts_is_an_invalid_selection() -> None:
    built = lesser_of_service(lesser_of_manifest(()))

    with pytest.raises(InvalidSelectionError, match="core/lesser_of.*'amounts'"):
        built.compose(EX_ON, 2025)


# --- core/greater_of: the greatest of a list of amounts, wired by a made-up manifest ------------
#
# `GreaterOf` is imported inside a cached factory, like `Sum` above, so its absence fails only the
# tests that use it. It is registered in a private registry under its shared identifier,
# `core/greater_of`, and reads the parts the made-up producers of the list-slot section make.


@cache
def greater_of_class() -> Any:
    from tax_engine.domain.capabilities.greater_of import GreaterOf

    return GreaterOf


def greater_of_manifest(amounts: tuple[str, ...]) -> Manifest:
    """The made-up producers of the wired parts and `core/greater_of` over `amounts`.

    Only producers whose part is wired are selected (part three is made from part one), so the
    composition has no orphan output.
    """
    to_one = CapabilitySelection(
        name="ex/scale",
        params={"factor": "ex/factor"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_one"},
    )
    to_two = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/base"},
        produces={"target": "ex/part_two"},
    )
    to_three = CapabilitySelection(
        name="ex/shift",
        params={"offset": "ex-on/offset"},
        consumes={"source": "ex/part_one"},
        produces={"target": "ex/part_three"},
    )
    greater = CapabilitySelection(
        name="core/greater_of",
        params={},
        consumes={"amounts": amounts},
        produces={"output": "ex-on/result"},
    )
    producers = {"ex/part_one": to_one, "ex/part_two": to_two, "ex/part_three": to_three}
    wired = set(amounts) | ({"ex/part_one"} if "ex/part_three" in amounts else set())
    selected = [selection for part, selection in producers.items() if part in wired]
    return manifest(greater, *reversed(selected))


def greater_of_service(*manifests: Manifest) -> TaxComputationService:
    capabilities = capability_registry()
    capabilities.register("core/greater_of", greater_of_class())
    artifacts = artifact_registry()
    for kind in (PART_ONE, PART_TWO, PART_THREE):
        artifacts.register(kind.identifier, kind)
    return service(*manifests, capabilities=capabilities, artifacts=artifacts)


def test_computes_core_greater_of_three_amounts_end_to_end() -> None:
    from tax_engine.domain.trace import GreaterOfLine

    amounts = ("ex/part_three", "ex/part_two", "ex/part_one")

    worksheet = greater_of_service(greater_of_manifest(amounts)).compute(
        EX_ON, 2025, Artifact(BASE, D("5"))
    )["ex-on/return"][0]

    # part_one = 5 × 3 = 15; part_two = 5 + 1 = 6; part_three = 15 + 1 = 16; the greatest is 16.
    assert worksheet.get(RESULT).value == D("16")
    assert isinstance(worksheet.producer_of(RESULT), greater_of_class())
    assert worksheet.trace[-1] == GreaterOfLine(
        RESULT, ((PART_THREE, D("16")), (PART_TWO, D("6")), (PART_ONE, D("15"))), D("16")
    )
    assert [type(line) for line in worksheet.trace].count(GreaterOfLine) == 1


def test_computes_core_greater_of_two_amounts_end_to_end() -> None:
    from tax_engine.domain.trace import GreaterOfLine

    amounts = ("ex/part_three", "ex/part_one")

    worksheet = greater_of_service(greater_of_manifest(amounts)).compute(
        EX_ON, 2025, Artifact(BASE, D("5"))
    )["ex-on/return"][0]

    # part_one = 15 and part_three = 16: the greater is part_three's 16.
    assert worksheet.get(RESULT).value == D("16")
    assert worksheet.trace[-1] == GreaterOfLine(
        RESULT, ((PART_THREE, D("16")), (PART_ONE, D("15"))), D("16")
    )


def test_core_greater_of_runs_after_all_its_amounts() -> None:
    amounts = ("ex/part_three", "ex/part_two", "ex/part_one")

    composition = (
        greater_of_service(greater_of_manifest(amounts))
        .compose(EX_ON, 2025)
        .form("ex-on/return")
        .composition
    )

    assert type(composition.order[-1]) is greater_of_class()
    assert composition.order[-1].consumes == frozenset({PART_ONE, PART_TWO, PART_THREE})


def test_core_greater_of_with_no_amounts_is_an_invalid_selection() -> None:
    built = greater_of_service(greater_of_manifest(()))

    with pytest.raises(InvalidSelectionError, match="core/greater_of.*'amounts'"):
        built.compose(EX_ON, 2025)


# --- core/contribution_tier: a rate on a band of earnings, capped, by a made-up manifest -------
#
# `TieredContribution` is imported inside a cached factory, like `Sum` above, so its absence fails
# only the tests that use it. It is registered in a private registry under its shared identifier,
# `core/contribution_tier`, consumes `ex/scaled` (base × 3) as its earnings, and reads a made-up
# `contribution_tier` dataset: 10% of the earnings between 10 and 40, at most 2.5, rounded half-up
# to the cent.


@cache
def tiered_contribution_class() -> Any:
    from tax_engine.domain.capabilities.contribution_tier import TieredContribution

    return TieredContribution


def some_tier_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.contribution_tier import (
        CONTRIBUTION_TIER,
        ContributionTier,
    )
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/some_tier",
        tax_year=tax_year,
        kind=CONTRIBUTION_TIER,
        values=ContributionTier(Rate(D("0.1")), D("10"), D("40"), D("2.5")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/some_tier",),
    )


CONTRIBUTION_TIER_SELECTION = CapabilitySelection(
    name="core/contribution_tier",
    params={"tier": "ex/some_tier"},
    consumes={"earnings": "ex/scaled"},
    produces={"output": "ex-on/result"},
)


def tiered_contribution_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/contribution_tier", tiered_contribution_class())
    parameters = FakeParameters(factor_data(), offset_data(), some_tier_data())
    built = service(
        manifest(CONTRIBUTION_TIER_SELECTION, SCALE),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_contribution_tier_inside_the_band_end_to_end() -> None:
    from tax_engine.domain.parameters.contribution_tier import ContributionTier
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import ContributionTierLine

    built, _parameters = tiered_contribution_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5.005")))["ex-on/return"][0]

    # scaled = 5.005 × 3 = 15.015; contributory = 15.015 − 10 = 5.015; × 10% = 0.5015, rounded
    # half-up to 0.50, below the maximum of 2.5.
    assert worksheet.get(SCALED).value == D("15.015")
    assert worksheet.get(RESULT).value == D("0.50")
    assert isinstance(worksheet.producer_of(RESULT), tiered_contribution_class())
    assert worksheet.trace[-1] == ContributionTierLine(
        RESULT,
        SCALED,
        D("15.015"),
        ContributionTier(Rate(D("0.1")), D("10"), D("40"), D("2.5")),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("5.015"),
        D("0.50"),
    )
    assert [type(line) for line in worksheet.trace].count(ContributionTierLine) == 1


def test_computes_core_contribution_tier_above_the_band_end_to_end() -> None:
    from tax_engine.domain.parameters.contribution_tier import ContributionTier
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import ContributionTierLine

    built, _parameters = tiered_contribution_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("20")))["ex-on/return"][0]

    # scaled = 60, above the upper bound: contributory = 40 − 10 = 30; × 10% = 3.00, so the
    # maximum of 2.5 binds.
    assert worksheet.get(RESULT).value == D("2.5")
    assert worksheet.trace[-1] == ContributionTierLine(
        RESULT,
        SCALED,
        D("60"),
        ContributionTier(Rate(D("0.1")), D("10"), D("40"), D("2.5")),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("30"),
        D("2.5"),
    )


def test_computes_core_contribution_tier_below_the_band_end_to_end() -> None:
    built, _parameters = tiered_contribution_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("3")))["ex-on/return"][0]

    # scaled = 9, below the lower bound of 10: nothing is contributory, rounded to 0.00.
    assert worksheet.get(RESULT).value == D("0")
    assert str(worksheet.get(RESULT).value) == "0.00"


def test_core_contribution_tier_runs_after_its_earnings_are_produced() -> None:
    built, _parameters = tiered_contribution_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is tiered_contribution_class()
    assert composition.order[-1].consumes == frozenset({SCALED})


def test_core_contribution_tier_asks_for_its_dataset_as_a_contribution_tier() -> None:
    from tax_engine.domain.parameters.contribution_tier import CONTRIBUTION_TIER

    built, parameters = tiered_contribution_service()

    built.compose(EX_ON, 2025)

    assert ("ex/some_tier", 2025, CONTRIBUTION_TIER) in parameters.requests


# --- core/tiered_surcharge: tiered rates on the base over thresholds, by a made-up manifest ---
#
# Like `Sum` above, `TieredSurcharge` is imported inside a cached factory so its absence fails only
# the tests that use it, and is registered in a private registry under its shared identifier,
# `core/tiered_surcharge`. It reads a made-up `surcharge_tiers` dataset, 20% over 10 and 50% over
# 12, whose rule rounds each part half-up to the cent.


@cache
def tiered_surcharge_class() -> Any:
    from tax_engine.domain.capabilities.tiered_surcharge import TieredSurcharge

    return TieredSurcharge


def surcharge_tiers_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.parameters.surcharge_tiers import (
        SURCHARGE_TIERS,
        SurchargeTier,
        SurchargeTiers,
    )

    return ParameterDataset(
        family="ex/surcharge_tiers",
        tax_year=tax_year,
        kind=SURCHARGE_TIERS,
        values=SurchargeTiers(
            (SurchargeTier(D("10"), Rate(D("0.2"))), SurchargeTier(D("12"), Rate(D("0.5"))))
        ),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/surcharge_tiers",),
    )


TIERED_SURCHARGE = CapabilitySelection(
    name="core/tiered_surcharge",
    params={"tiers": "ex/surcharge_tiers"},
    consumes={"base": "ex/scaled"},
    produces={"output": "ex-on/result"},
)


def tiered_surcharge_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/tiered_surcharge", tiered_surcharge_class())
    parameters = FakeParameters(factor_data(), offset_data(), surcharge_tiers_data())
    built = service(
        manifest(TIERED_SURCHARGE, SCALE),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_tiered_surcharge_above_all_thresholds_end_to_end() -> None:
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import SurchargeTierLine

    built, _parameters = tiered_surcharge_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5.005")))["ex-on/return"][0]

    # scaled = 5.005 × 3 = 15.015; 20% of 5.015 = 1.003 -> 1.00, 50% of 3.015 = 1.5075 -> 1.51.
    cent = RoundTo(D("0.01"), RoundingMode.HALF_UP)
    assert worksheet.get(SCALED).value == D("15.015")
    assert worksheet.get(RESULT).value == D("2.51")
    assert isinstance(worksheet.producer_of(RESULT), tiered_surcharge_class())
    assert worksheet.trace[-2:] == (
        SurchargeTierLine(RESULT, SCALED, D("15.015"), D("10"), Rate(D("0.2")), cent, D("1.00")),
        SurchargeTierLine(RESULT, SCALED, D("15.015"), D("12"), Rate(D("0.5")), cent, D("1.51")),
    )
    assert [type(line) for line in worksheet.trace].count(SurchargeTierLine) == 2


def test_computes_core_tiered_surcharge_between_the_thresholds_end_to_end() -> None:
    from tax_engine.domain.trace import SurchargeTierLine

    built, _parameters = tiered_surcharge_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("3.5")))["ex-on/return"][0]

    # scaled = 10.5; 20% of 0.5 = 0.10, nothing over 12.
    assert worksheet.get(RESULT).value == D("0.10")
    lines = [line for line in worksheet.trace if isinstance(line, SurchargeTierLine)]
    assert [line.part for line in lines] == [D("0.10"), D("0")]


def test_computes_core_tiered_surcharge_below_the_first_threshold_end_to_end() -> None:
    built, _parameters = tiered_surcharge_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("3")))["ex-on/return"][0]

    # scaled = 9, below both thresholds: no surcharge.
    assert worksheet.get(RESULT).value == D("0")


def test_core_tiered_surcharge_runs_after_its_base_is_produced() -> None:
    built, _parameters = tiered_surcharge_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is tiered_surcharge_class()
    assert composition.order[-1].consumes == frozenset({SCALED})


def test_core_tiered_surcharge_asks_for_its_dataset_as_surcharge_tiers() -> None:
    from tax_engine.domain.parameters.surcharge_tiers import SURCHARGE_TIERS

    built, parameters = tiered_surcharge_service()

    built.compose(EX_ON, 2025)

    assert ("ex/surcharge_tiers", 2025, SURCHARGE_TIERS) in parameters.requests


# The same capability over a made-up `surcharge_tiers` dataset whose tiers each have a maximum:
# 20% over 10 at most 0.50, and 50% over 12 at most 1, each part rounded half-up to the cent.


def capped_surcharge_tiers_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.parameters.surcharge_tiers import (
        SURCHARGE_TIERS,
        SurchargeTier,
        SurchargeTiers,
    )

    return ParameterDataset(
        family="ex/surcharge_tiers",
        tax_year=tax_year,
        kind=SURCHARGE_TIERS,
        values=SurchargeTiers(
            (
                SurchargeTier(D("10"), Rate(D("0.2")), D("0.50")),
                SurchargeTier(D("12"), Rate(D("0.5")), D("1")),
            )
        ),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/surcharge_tiers",),
    )


def capped_surcharge_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/tiered_surcharge", tiered_surcharge_class())
    parameters = FakeParameters(factor_data(), offset_data(), capped_surcharge_tiers_data())
    built = service(
        manifest(TIERED_SURCHARGE, SCALE),
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_tiered_surcharge_with_every_tier_at_its_maximum_end_to_end() -> None:
    from tax_engine.domain.parameters.rate import Rate
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import SurchargeTierLine

    built, _parameters = capped_surcharge_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5.005")))["ex-on/return"][0]

    # scaled = 15.015; 20% of 5.015 = 1.003, at most 0.50; 50% of 3.015 = 1.5075, at most 1
    # -> 1.00.
    cent = RoundTo(D("0.01"), RoundingMode.HALF_UP)
    assert worksheet.get(RESULT).value == D("1.50")
    assert worksheet.trace[-2:] == (
        SurchargeTierLine(
            RESULT, SCALED, D("15.015"), D("10"), Rate(D("0.2")), cent, D("0.50"), D("0.50")
        ),
        SurchargeTierLine(
            RESULT, SCALED, D("15.015"), D("12"), Rate(D("0.5")), cent, D("1.00"), D("1")
        ),
    )


def test_computes_core_tiered_surcharge_with_one_tier_at_its_maximum_end_to_end() -> None:
    from tax_engine.domain.trace import SurchargeTierLine

    built, _parameters = capped_surcharge_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("4.2")))["ex-on/return"][0]

    # scaled = 12.6; 20% of 2.6 = 0.52, at most 0.50; 50% of 0.6 = 0.30, under its maximum.
    assert worksheet.get(RESULT).value == D("0.80")
    lines = [line for line in worksheet.trace if isinstance(line, SurchargeTierLine)]
    assert [(line.part, line.maximum) for line in lines] == [
        (D("0.50"), D("0.50")),
        (D("0.30"), D("1")),
    ]


def test_computes_core_tiered_surcharge_under_every_maximum_end_to_end() -> None:
    built, _parameters = capped_surcharge_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("3.5")))["ex-on/return"][0]

    # scaled = 10.5; 20% of 0.5 = 0.10, under its maximum; nothing over 12.
    assert worksheet.get(RESULT).value == D("0.10")


# --- core/tapered_amount: a base plus a supplement tapered by a figure, by a made-up manifest --
#
# Like `Sum` above, `TaperedAmount` is imported inside a cached factory so its absence fails only
# the tests that use it, and is registered in a private registry under its shared identifier,
# `core/tapered_amount`. It consumes `ex/scaled` (base × 3) and reads a made-up `taper` dataset:
# 10 plus 5, the 5 reduced to nothing as the scaled figure goes from 20 to 30, rounded half-up to
# the cent.


@cache
def tapered_amount_class() -> Any:
    from tax_engine.domain.capabilities.tapered_amount import TaperedAmount

    return TaperedAmount


def some_taper_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.parameters.taper import TAPER, Taper

    return ParameterDataset(
        family="ex/some_taper",
        tax_year=tax_year,
        kind=TAPER,
        values=Taper(D("10"), D("5"), D("20"), D("10")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/some_taper",),
    )


TAPERED_AMOUNT = CapabilitySelection(
    name="core/tapered_amount",
    params={"taper": "ex/some_taper"},
    consumes={"base": "ex/scaled"},
    produces={"output": "ex-on/result"},
)


def tapered_amount_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/tapered_amount", tapered_amount_class())
    parameters = FakeParameters(factor_data(), offset_data(), some_taper_data())
    built = service(
        manifest(TAPERED_AMOUNT, SCALE),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_tapered_amount_inside_the_range_end_to_end() -> None:
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.parameters.taper import Taper
    from tax_engine.domain.trace import TaperedAmountLine

    built, _parameters = tapered_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("7.001")))["ex-on/return"][0]

    # scaled = 7.001 × 3 = 21.003; reduction = 5 × 1.003 / 10 = 0.5015; 10 + (5 − 0.5015) =
    # 14.4985, rounded half-up to 14.50.
    assert worksheet.get(SCALED).value == D("21.003")
    assert worksheet.get(RESULT).value == D("14.50")
    assert isinstance(worksheet.producer_of(RESULT), tapered_amount_class())
    assert worksheet.trace[-1] == TaperedAmountLine(
        RESULT,
        SCALED,
        D("21.003"),
        Taper(D("10"), D("5"), D("20"), D("10")),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        ExactFraction("0.5015"),
        D("14.50"),
    )
    assert [type(line) for line in worksheet.trace].count(TaperedAmountLine) == 1


def test_computes_core_tapered_amount_above_the_range_end_to_end() -> None:
    from tax_engine.domain.trace import TaperedAmountLine

    built, _parameters = tapered_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("20")))["ex-on/return"][0]

    # scaled = 60, past 20 + 10: reduction = 5 × 40 / 10 = 20, so only the base amount is left.
    assert worksheet.get(RESULT).value == D("10")
    assert str(worksheet.get(RESULT).value) == "10.00"
    (line,) = [line for line in worksheet.trace if isinstance(line, TaperedAmountLine)]
    assert line.reduction == ExactFraction(20)
    assert isinstance(line.reduction, ExactFraction)


def test_computes_core_tapered_amount_below_the_threshold_end_to_end() -> None:
    built, _parameters = tapered_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5")))["ex-on/return"][0]

    # scaled = 15, below the threshold of 20: the full 10 + 5, rounded to 15.00.
    assert worksheet.get(RESULT).value == D("15")
    assert str(worksheet.get(RESULT).value) == "15.00"


def test_core_tapered_amount_runs_after_its_base_is_produced() -> None:
    built, _parameters = tapered_amount_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is tapered_amount_class()
    assert composition.order[-1].consumes == frozenset({SCALED})


def test_core_tapered_amount_asks_for_its_dataset_as_a_taper() -> None:
    from tax_engine.domain.parameters.taper import TAPER

    built, parameters = tapered_amount_service()

    built.compose(EX_ON, 2025)

    assert ("ex/some_taper", 2025, TAPER) in parameters.requests


# --- core/per_unit_amount: an amount dataset's amount for each of a count, by a made-up manifest -
#
# Like `Sum` above, `PerUnitAmount` is imported inside a cached factory so its absence fails only
# the tests that use it, and is registered in a private registry under its shared identifier,
# `core/per_unit_amount`. It consumes `ex/count`, a made-up `int` input, and reads a made-up
# `amount` dataset of 544.5 for each unit, rounded half-up to the cent.

COUNT = ArtifactKind("ex/count", int)


@cache
def per_unit_amount_class() -> Any:
    from tax_engine.domain.capabilities.per_unit_amount import PerUnitAmount

    return PerUnitAmount


def some_amount_per_unit_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.amount import AMOUNT, Amount
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/some_amount_per_unit",
        tax_year=tax_year,
        kind=AMOUNT,
        values=Amount(D("544.5")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/some_amount_per_unit",),
    )


PER_UNIT_AMOUNT = CapabilitySelection(
    name="core/per_unit_amount",
    params={"amount": "ex/some_amount_per_unit"},
    consumes={"count": "ex/count"},
    produces={"output": "ex-on/result"},
)


def per_unit_amount_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/per_unit_amount", per_unit_amount_class())
    artifacts = artifact_registry()
    artifacts.register(COUNT.identifier, COUNT)
    parameters = FakeParameters(factor_data(), offset_data(), some_amount_per_unit_data())
    built = service(
        manifest(PER_UNIT_AMOUNT, inputs=frozenset({"ex/count"})),
        parameters=parameters,
        capabilities=capabilities,
        artifacts=artifacts,
    )
    return built, parameters


def test_computes_core_per_unit_amount_end_to_end() -> None:
    from tax_engine.domain.parameters.amount import Amount
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import PerUnitAmountLine

    built, _parameters = per_unit_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(COUNT, 3))["ex-on/return"][0]

    # 544.5 × 3 = 1633.5, rounded half-up to the cent: 1633.50.
    assert worksheet.get(RESULT).value == D("1633.5")
    assert str(worksheet.get(RESULT).value) == "1633.50"
    assert isinstance(worksheet.producer_of(RESULT), per_unit_amount_class())
    assert worksheet.producer_of(COUNT) is None
    assert worksheet.trace == (
        PerUnitAmountLine(
            RESULT,
            COUNT,
            3,
            Amount(D("544.5")),
            RoundTo(D("0.01"), RoundingMode.HALF_UP),
            D("1633.50"),
        ),
    )


def test_computes_core_per_unit_amount_for_a_count_of_zero_end_to_end() -> None:
    built, _parameters = per_unit_amount_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(COUNT, 0))["ex-on/return"][0]

    assert worksheet.get(RESULT).value == D("0")


def test_core_per_unit_amount_consumes_its_count_as_an_int() -> None:
    built, _parameters = per_unit_amount_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    (only,) = composition.order
    assert type(only) is per_unit_amount_class()
    assert only.consumes == frozenset({COUNT})


def test_core_per_unit_amount_rejects_a_money_input_for_its_count() -> None:
    built, _parameters = per_unit_amount_service()

    with pytest.raises(InvalidCompositionError, match="'count' was given as Decimal but the input"):
        built.compute(EX_ON, 2025, Artifact(ArtifactKind("ex/count", Decimal), D("3")))


def test_core_per_unit_amount_asks_for_its_dataset_as_an_amount() -> None:
    from tax_engine.domain.parameters.amount import AMOUNT

    built, parameters = per_unit_amount_service()

    built.compose(EX_ON, 2025)

    assert ("ex/some_amount_per_unit", 2025, AMOUNT) in parameters.requests


# --- core/amount_by_count: a table's amount for a count, by a made-up manifest -----------------
#
# Like `PerUnitAmount` above, `AmountForCount` is imported inside a cached factory so its absence
# fails only the tests that use it, and is registered in a private registry under its shared
# identifier, `core/amount_by_count`. It consumes `ex/count`, a made-up `int` input, and reads a
# made-up `amount_by_count` dataset with a row for each count from 1 to 4, rounded half-up to the
# cent.


@cache
def amount_by_count_class() -> Any:
    from tax_engine.domain.capabilities.amount_by_count import AmountForCount

    return AmountForCount


def some_amount_by_count_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.amount_by_count import AMOUNT_BY_COUNT, AmountByCount
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/some_amount_by_count",
        tax_year=tax_year,
        kind=AMOUNT_BY_COUNT,
        values=AmountByCount(((1, D("100")), (2, D("200.50")), (3, D("300")), (4, D("400.255")))),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/some_amount_by_count",),
    )


AMOUNT_BY_COUNT_SELECTION = CapabilitySelection(
    name="core/amount_by_count",
    params={"table": "ex/some_amount_by_count"},
    consumes={"count": "ex/count"},
    produces={"output": "ex-on/result"},
)


def amount_by_count_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/amount_by_count", amount_by_count_class())
    artifacts = artifact_registry()
    artifacts.register(COUNT.identifier, COUNT)
    parameters = FakeParameters(factor_data(), offset_data(), some_amount_by_count_data())
    built = service(
        manifest(AMOUNT_BY_COUNT_SELECTION, inputs=frozenset({"ex/count"})),
        parameters=parameters,
        capabilities=capabilities,
        artifacts=artifacts,
    )
    return built, parameters


def test_computes_core_amount_by_count_end_to_end() -> None:
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import AmountByCountLine

    built, _parameters = amount_by_count_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(COUNT, 2))["ex-on/return"][0]

    # The row for 2 is 200.50, already at the cent.
    assert worksheet.get(RESULT).value == D("200.5")
    assert str(worksheet.get(RESULT).value) == "200.50"
    assert isinstance(worksheet.producer_of(RESULT), amount_by_count_class())
    assert worksheet.producer_of(COUNT) is None
    assert worksheet.trace == (
        AmountByCountLine(
            RESULT,
            COUNT,
            2,
            D("200.50"),
            RoundTo(D("0.01"), RoundingMode.HALF_UP),
            D("200.50"),
        ),
    )


def test_computes_core_amount_by_count_rounding_the_row_end_to_end() -> None:
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import AmountByCountLine

    built, _parameters = amount_by_count_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(COUNT, 4))["ex-on/return"][0]

    # The row for 4 is 400.255, half-up to 400.26.
    assert worksheet.get(RESULT).value == D("400.26")
    assert worksheet.trace[-1] == AmountByCountLine(
        RESULT, COUNT, 4, D("400.255"), RoundTo(D("0.01"), RoundingMode.HALF_UP), D("400.26")
    )


def test_core_amount_by_count_refuses_a_count_without_a_row_end_to_end() -> None:
    from tax_engine.domain.errors import NoAmountForCountError

    built, _parameters = amount_by_count_service()

    with pytest.raises(NoAmountForCountError, match="count 0"):
        built.compute(EX_ON, 2025, Artifact(COUNT, 0))
    with pytest.raises(NoAmountForCountError, match="count 5"):
        built.compute(EX_ON, 2025, Artifact(COUNT, 5))


def test_core_amount_by_count_consumes_its_count_as_an_int() -> None:
    built, _parameters = amount_by_count_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    (only,) = composition.order
    assert type(only) is amount_by_count_class()
    assert only.consumes == frozenset({COUNT})


def test_core_amount_by_count_rejects_a_money_input_for_its_count() -> None:
    built, _parameters = amount_by_count_service()

    with pytest.raises(InvalidCompositionError, match="'count' was given as Decimal but the input"):
        built.compute(EX_ON, 2025, Artifact(ArtifactKind("ex/count", Decimal), D("3")))


def test_core_amount_by_count_asks_for_its_dataset_as_an_amount_by_count() -> None:
    from tax_engine.domain.parameters.amount_by_count import AMOUNT_BY_COUNT

    built, parameters = amount_by_count_service()

    built.compose(EX_ON, 2025)

    assert ("ex/some_amount_by_count", 2025, AMOUNT_BY_COUNT) in parameters.requests


# --- core/multiple_over: a factor of one amount over another, not below 0, by a made-up manifest -
#
# Like `Sum` above, `MultipleOver` is imported inside a cached factory so its absence fails only
# the tests that use it, and is registered in a private registry under its shared identifier,
# `core/multiple_over`. It multiplies `ex/scaled` (base × 3) by a made-up `factor` dataset of 2,
# takes off the `ex/extra` input, floors at zero and rounds half-up to the cent. The real `factor`
# kind shares its name with this file's made-up `FACTOR`, so it is imported under another name.


@cache
def multiple_over_class() -> Any:
    from tax_engine.domain.capabilities.multiple_over import MultipleOver

    return MultipleOver


def some_factor_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.factor import FACTOR as FACTOR_KIND
    from tax_engine.domain.parameters.factor import Factor as FactorValue
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/some_factor",
        tax_year=tax_year,
        kind=FACTOR_KIND,
        values=FactorValue(D("2")),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/some_factor",),
    )


MULTIPLE_OVER = CapabilitySelection(
    name="core/multiple_over",
    params={"factor": "ex/some_factor"},
    consumes={"amount": "ex/scaled", "less": "ex/extra"},
    produces={"output": "ex-on/result"},
)


def multiple_over_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/multiple_over", multiple_over_class())
    parameters = FakeParameters(factor_data(), offset_data(), some_factor_data())
    built = service(
        manifest(  # authored out of order on purpose
            MULTIPLE_OVER, SCALE, inputs=frozenset({"ex/base", "ex/extra"})
        ),
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_multiple_over_above_the_figure_end_to_end() -> None:
    from tax_engine.domain.parameters.factor import Factor as FactorValue
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import MultipleOverLine

    built, _parameters = multiple_over_service()

    worksheet = built.compute(
        EX_ON, 2025, Artifact(BASE, D("100.005")), Artifact(EXTRA, D("150.0125"))
    )["ex-on/return"][0]

    # scaled = 100.005 × 3 = 300.015; 2 × 300.015 = 600.030, less 150.0125 = 450.0175, rounded
    # half-up to 450.02.
    assert worksheet.get(SCALED).value == D("300.015")
    assert worksheet.get(RESULT).value == D("450.02")
    assert isinstance(worksheet.producer_of(RESULT), multiple_over_class())
    assert worksheet.trace[-1] == MultipleOverLine(
        RESULT,
        SCALED,
        D("300.015"),
        FactorValue(D("2")),
        EXTRA,
        D("150.0125"),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("450.02"),
    )
    assert [type(line) for line in worksheet.trace].count(MultipleOverLine) == 1


def test_computes_core_multiple_over_floored_at_zero_end_to_end() -> None:
    from tax_engine.domain.trace import MultipleOverLine

    built, _parameters = multiple_over_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("100")), Artifact(EXTRA, D("700")))[
        "ex-on/return"
    ][0]

    # 2 × 300 = 600, less 700 is below zero: 0, rounded to 0.00.
    assert worksheet.get(RESULT).value == D("0")
    assert str(worksheet.get(RESULT).value) == "0.00"
    (line,) = [line for line in worksheet.trace if isinstance(line, MultipleOverLine)]
    assert line.less_amount == D("700")


def test_core_multiple_over_runs_after_its_amount_is_produced() -> None:
    built, _parameters = multiple_over_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is multiple_over_class()
    assert composition.order[-1].consumes == frozenset({SCALED, EXTRA})


def test_core_multiple_over_asks_for_its_dataset_as_a_factor() -> None:
    from tax_engine.domain.parameters.factor import FACTOR as FACTOR_KIND

    built, parameters = multiple_over_service()

    built.compose(EX_ON, 2025)

    assert ("ex/some_factor", 2025, FACTOR_KIND) in parameters.requests
    assert ("ex/some_factor", 2025, FACTOR) not in parameters.requests  # not the made-up kind


# --- core/per_unit_amount into core/multiple_over, by a made-up manifest ------------------------
#
# The two together, as a form's "number multiplied by an amount", then "multiplied by 2", then
# "minus" another line, "if negative, enter 0": the count's amount is the multiple's `amount`
# and the scaled base is taken off.


def per_unit_into_multiple_over_service() -> TaxComputationService:
    per_unit = CapabilitySelection(
        name="core/per_unit_amount",
        params={"amount": "ex/some_amount_per_unit"},
        consumes={"count": "ex/count"},
        produces={"output": "ex/part_one"},
    )
    multiple = CapabilitySelection(
        name="core/multiple_over",
        params={"factor": "ex/some_factor"},
        consumes={"amount": "ex/part_one", "less": "ex/scaled"},
        produces={"output": "ex-on/result"},
    )
    capabilities = capability_registry()
    capabilities.register("core/per_unit_amount", per_unit_amount_class())
    capabilities.register("core/multiple_over", multiple_over_class())
    artifacts = artifact_registry()
    for kind in (COUNT, PART_ONE):
        artifacts.register(kind.identifier, kind)
    parameters = FakeParameters(
        factor_data(), offset_data(), some_amount_per_unit_data(), some_factor_data()
    )
    return service(
        manifest(  # authored out of order on purpose
            multiple, SCALE, per_unit, inputs=frozenset({"ex/base", "ex/count"})
        ),
        parameters=parameters,
        capabilities=capabilities,
        artifacts=artifacts,
    )


def test_computes_core_per_unit_amount_into_core_multiple_over_end_to_end() -> None:
    worksheet = per_unit_into_multiple_over_service().compute(
        EX_ON, 2025, Artifact(BASE, D("100")), Artifact(COUNT, 2)
    )["ex-on/return"][0]

    # part_one = 544.5 × 2 = 1089.0, to 1089.00; scaled = 300; 2 × 1089.00 − 300 = 1878.00.
    assert worksheet.get(PART_ONE).value == D("1089")
    assert worksheet.get(SCALED).value == D("300")
    assert worksheet.get(RESULT).value == D("1878")
    assert str(worksheet.get(RESULT).value) == "1878.00"


def test_computes_core_per_unit_amount_into_core_multiple_over_with_no_units() -> None:
    worksheet = per_unit_into_multiple_over_service().compute(
        EX_ON, 2025, Artifact(BASE, D("100")), Artifact(COUNT, 0)
    )["ex-on/return"][0]

    # part_one = 0; 2 × 0 − 300 is below zero: 0.
    assert worksheet.get(RESULT).value == D("0")


# --- core/at_most: an amount that may not exceed a bound, wired by a made-up manifest ----------
#
# Like `Subtract` above, `AtMost` is imported inside a cached factory so its absence fails only
# the tests that use it, and is registered in a private registry under its shared identifier,
# `core/at_most`. Its amount is one of the manifest's inputs, as a claim a filer gives, and its
# bound is a produced artifact.


@cache
def at_most_class() -> Any:
    from tax_engine.domain.capabilities.at_most import AtMost

    return AtMost


def at_most_service() -> TaxComputationService:
    """`ex/scale` (base × 3) and `core/at_most` producing `ex-on/result` = extra, at most scaled."""
    at_most = CapabilitySelection(
        name="core/at_most",
        params={},
        consumes={"amount": "ex/extra", "bound": "ex/scaled"},
        produces={"output": "ex-on/result"},
    )
    capabilities = capability_registry()
    capabilities.register("core/at_most", at_most_class())
    return service(  # authored out of order on purpose
        manifest(at_most, SCALE, inputs=frozenset({"ex/base", "ex/extra"})),
        capabilities=capabilities,
    )


def test_computes_core_at_most_below_the_bound_end_to_end() -> None:
    from tax_engine.domain.trace import AtMostLine

    worksheet = at_most_service().compute(
        EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("10.50"))
    )["ex-on/return"][0]

    # scaled = 5 × 3 = 15; extra 10.50 is at most 15, so result = 10.50, unchanged.
    assert worksheet.get(RESULT).value == D("10.50")
    assert str(worksheet.get(RESULT).value) == "10.50"
    assert isinstance(worksheet.producer_of(RESULT), at_most_class())
    assert worksheet.trace[-1] == AtMostLine(RESULT, EXTRA, D("10.50"), SCALED, D("15"))
    assert [type(line) for line in worksheet.trace].count(AtMostLine) == 1


def test_computes_core_at_most_equal_to_the_bound_end_to_end() -> None:
    from tax_engine.domain.trace import AtMostLine

    worksheet = at_most_service().compute(
        EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("15"))
    )["ex-on/return"][0]

    # scaled = 15 and extra = 15: at most the bound, so result = 15.
    assert worksheet.get(RESULT).value == D("15")
    assert worksheet.trace[-1] == AtMostLine(RESULT, EXTRA, D("15"), SCALED, D("15"))


def test_core_at_most_above_the_bound_raises_naming_both_kinds_end_to_end() -> None:
    from tax_engine.domain.errors import InputAboveBoundError

    built = at_most_service()

    # scaled = 15; extra 15.01 is above it: an input error, not a capped result.
    with pytest.raises(InputAboveBoundError) as raised:
        built.compute(EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("15.01")))

    assert str(raised.value) == ("ex-on/return, instance 1: ex/extra 15.01 is above ex/scaled 15")


def test_core_at_most_runs_after_what_it_consumes_is_produced() -> None:
    composition = at_most_service().compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is at_most_class()
    assert composition.order[-1].consumes == frozenset({EXTRA, SCALED})


# --- core/apply_fraction: base × a fraction dataset's fraction, by a made-up manifest ----------
#
# Like `Sum` above, `ApplyFraction` is imported inside a cached factory so its absence fails only
# the tests that use it, and is registered in a private registry under its shared identifier,
# `core/apply_fraction`. It consumes `ex/scaled` (base × 3) and reads a made-up `fraction`
# dataset of five-sevenths that rounds half-up to the cent, so the quotient is inexact.


@cache
def apply_fraction_class() -> Any:
    from tax_engine.domain.capabilities.apply_fraction import ApplyFraction

    return ApplyFraction


def portion_fraction_data(tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.fraction import FRACTION, Fraction
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo

    return ParameterDataset(
        family="ex/portion_fraction",
        tax_year=tax_year,
        kind=FRACTION,
        values=Fraction(5, 7),
        rounding=RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/portion_fraction",),
    )


APPLY_FRACTION = CapabilitySelection(
    name="core/apply_fraction",
    params={"fraction": "ex/portion_fraction"},
    consumes={"base": "ex/scaled"},
    produces={"output": "ex-on/result"},
)


def apply_fraction_service() -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/apply_fraction", apply_fraction_class())
    parameters = FakeParameters(factor_data(), offset_data(), portion_fraction_data())
    built = service(
        manifest(APPLY_FRACTION, SCALE),  # authored out of order on purpose
        parameters=parameters,
        capabilities=capabilities,
    )
    return built, parameters


def test_computes_core_apply_fraction_end_to_end() -> None:
    from tax_engine.domain.parameters.fraction import Fraction
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import FractionAppliedLine

    built, _parameters = apply_fraction_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5")))["ex-on/return"][0]

    # scaled = 5 × 3 = 15; result = 15 × 5 / 7 = 10.714285..., rounded half-up to 10.71.
    assert worksheet.get(SCALED).value == D("15")
    assert worksheet.get(RESULT).value == D("10.71")
    assert isinstance(worksheet.producer_of(RESULT), apply_fraction_class())
    assert worksheet.trace[-1] == FractionAppliedLine(
        RESULT,
        SCALED,
        D("15"),
        Fraction(5, 7),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("10.71"),
    )
    assert [type(line) for line in worksheet.trace].count(FractionAppliedLine) == 1


def test_computes_core_apply_fraction_to_an_exact_quotient_end_to_end() -> None:
    built, _parameters = apply_fraction_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("7")))["ex-on/return"][0]

    # scaled = 21; result = 21 × 5 / 7 = 15 exactly, rounded to 15.00.
    assert worksheet.get(RESULT).value == D("15")
    assert str(worksheet.get(RESULT).value) == "15.00"


def test_core_apply_fraction_with_an_inexact_quotient_and_no_rounding_names_the_capability() -> (
    None
):
    from tax_engine.domain.errors import CapabilityContractError
    from tax_engine.domain.parameters.fraction import FRACTION, Fraction

    capabilities = capability_registry()
    capabilities.register("core/apply_fraction", apply_fraction_class())
    unrounded = ParameterDataset(
        family="ex/portion_fraction",
        tax_year=2025,
        kind=FRACTION,
        values=Fraction(5, 7),
        rounding=NO_ROUNDING,
        sources=("https://example.org/ex/portion_fraction",),
    )
    built = service(
        manifest(APPLY_FRACTION, SCALE),
        parameters=FakeParameters(factor_data(), offset_data(), unrounded),
        capabilities=capabilities,
    )

    # scaled = 15; 15 × 5 / 7 has no finite expansion and the dataset states no rounding.
    with pytest.raises(CapabilityContractError, match=r"ApplyFraction .*inexact") as raised:
        built.compute(EX_ON, 2025, Artifact(BASE, D("5")))

    assert isinstance(raised.value.__cause__, decimal.Inexact)


def test_core_apply_fraction_runs_after_its_base_is_produced() -> None:
    built, _parameters = apply_fraction_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is apply_fraction_class()
    assert composition.order[-1].consumes == frozenset({SCALED})


def test_core_apply_fraction_asks_for_its_dataset_as_a_fraction() -> None:
    from tax_engine.domain.parameters.fraction import FRACTION

    built, parameters = apply_fraction_service()

    built.compose(EX_ON, 2025)

    assert ("ex/portion_fraction", 2025, FRACTION) in parameters.requests


# --- core/apply_ratio: an amount times a ratio of two artifacts, by a made-up manifest ---------
#
# Like `ApplyFraction` above, `ApplyRatio` is imported inside a cached factory so its absence fails
# only the tests that use it, and is registered in a private registry under its shared
# identifier, `core/apply_ratio`. Its amount is a produced artifact, `ex/scaled` (base × 3), its
# numerator is `ex/base` and its denominator is `ex/extra`, a made-up input. It reads a made-up
# `rounding_only` dataset that rounds half-up to the cent, so the quotient is inexact.


@cache
def apply_ratio_class() -> Any:
    from tax_engine.domain.capabilities.apply_ratio import ApplyRatio

    return ApplyRatio


def ratio_rounding_data(rounding: Any = None, tax_year: int = 2025) -> ParameterDataset[Any]:
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY, RoundingOnly

    return ParameterDataset(
        family="ex/ratio_rounding",
        tax_year=tax_year,
        kind=ROUNDING_ONLY,
        values=RoundingOnly(),
        rounding=rounding or RoundTo(D("0.01"), RoundingMode.HALF_UP),
        sources=("https://example.org/ex/ratio_rounding",),
    )


APPLY_RATIO = CapabilitySelection(
    name="core/apply_ratio",
    params={"rounding": "ex/ratio_rounding"},
    consumes={"amount": "ex/scaled", "numerator": "ex/base", "denominator": "ex/extra"},
    produces={"output": "ex-on/result"},
)


def apply_ratio_service(
    selection: CapabilitySelection = APPLY_RATIO, rounding: Any = None
) -> tuple[TaxComputationService, FakeParameters]:
    capabilities = capability_registry()
    capabilities.register("core/apply_ratio", apply_ratio_class())
    parameters = FakeParameters(factor_data(), offset_data(), ratio_rounding_data(rounding))
    artifacts = artifact_registry()
    artifacts.register(PERSON_COUNT.identifier, PERSON_COUNT)
    built = service(
        manifest(selection, SCALE, inputs=frozenset({"ex/base", "ex/extra"})),  # out of order
        parameters=parameters,
        capabilities=capabilities,
        artifacts=artifacts,
    )
    return built, parameters


def test_computes_core_apply_ratio_end_to_end() -> None:
    from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
    from tax_engine.domain.trace import RatioAppliedLine

    built, _parameters = apply_ratio_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("7")))[
        "ex-on/return"
    ][0]

    # scaled = 5 × 3 = 15; result = 15 × 5 / 7 = 10.714285..., rounded half-up to 10.71.
    assert worksheet.get(SCALED).value == D("15")
    assert worksheet.get(RESULT).value == D("10.71")
    assert isinstance(worksheet.producer_of(RESULT), apply_ratio_class())
    assert worksheet.trace[-1] == RatioAppliedLine(
        RESULT,
        SCALED,
        D("15"),
        BASE,
        D("5"),
        EXTRA,
        D("7"),
        RoundTo(D("0.01"), RoundingMode.HALF_UP),
        D("10.71"),
    )
    assert [type(line) for line in worksheet.trace].count(RatioAppliedLine) == 1


def test_computes_core_apply_ratio_to_an_exact_quotient_end_to_end() -> None:
    built, _parameters = apply_ratio_service()

    worksheet = built.compute(EX_ON, 2025, Artifact(BASE, D("7")), Artifact(EXTRA, D("3")))[
        "ex-on/return"
    ][0]

    # scaled = 21; result = 21 × 7 / 3 = 49 exactly, rounded to 49.00.
    assert worksheet.get(RESULT).value == D("49")
    assert str(worksheet.get(RESULT).value) == "49.00"


def test_core_apply_ratio_with_an_inexact_quotient_and_no_rounding_names_the_capability() -> None:
    from tax_engine.domain.errors import CapabilityContractError

    built, _parameters = apply_ratio_service(rounding=NO_ROUNDING)

    # scaled = 15; 15 × 5 / 7 has no finite expansion and the dataset states no rounding.
    with pytest.raises(CapabilityContractError, match=r"ApplyRatio .*inexact") as raised:
        built.compute(EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("7")))

    assert isinstance(raised.value.__cause__, decimal.Inexact)


def test_core_apply_ratio_with_a_zero_denominator_is_a_validation_error_end_to_end() -> None:
    from tax_engine.domain.errors import ValidationError

    built, _parameters = apply_ratio_service()

    with pytest.raises(ValidationError) as raised:
        built.compute(EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("0")))

    message = str(raised.value)
    assert "ex/scaled" in message
    assert "ex/base" in message
    assert "ex/extra" in message


def test_core_apply_ratio_runs_after_what_it_consumes_is_produced() -> None:
    built, _parameters = apply_ratio_service()

    composition = built.compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is apply_ratio_class()
    assert composition.order[-1].consumes == frozenset({SCALED, BASE, EXTRA})


def test_core_apply_ratio_asks_for_its_dataset_as_rounding_only() -> None:
    from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY

    built, parameters = apply_ratio_service()

    built.compose(EX_ON, 2025)

    assert ("ex/ratio_rounding", 2025, ROUNDING_ONLY) in parameters.requests


def test_core_apply_ratio_refuses_a_count_kind_for_its_amount_at_wiring() -> None:
    selection = CapabilitySelection(
        name="core/apply_ratio",
        params={"rounding": "ex/ratio_rounding"},
        consumes={"amount": "ex/person_count", "numerator": "ex/base", "denominator": "ex/extra"},
        produces={"output": "ex-on/result"},
    )
    built, _parameters = apply_ratio_service(selection)

    with pytest.raises(InvalidSelectionError, match="core/apply_ratio.*'amount'"):
        built.compose(EX_ON, 2025)


# --- core/times_count: an artifact's amount for each of a count, by a made-up manifest ---------
#
# Like `PerUnitAmount` above, `TimesCount` is imported inside a cached factory so its absence fails
# only the tests that use it, and is registered in a private registry under its shared
# identifier, `core/times_count`. Its amount is a produced artifact, `ex/scaled` (base × 3), and
# its count is `ex/count`, a made-up `int` input; it reads no dataset.

PERSON_COUNT = ArtifactKind("ex/person_count", int)


@cache
def times_count_class() -> Any:
    from tax_engine.domain.capabilities.times_count import TimesCount

    return TimesCount


def times_count_selection(
    amount: str = "ex/scaled", count: str = "ex/count"
) -> CapabilitySelection:
    return CapabilitySelection(
        name="core/times_count",
        params={},
        consumes={"amount": amount, "count": count},
        produces={"output": "ex-on/result"},
    )


def times_count_service(
    selection: CapabilitySelection | None = None,
) -> TaxComputationService:
    """`ex/scale` (base × 3) and `core/times_count` producing `ex-on/result` = scaled × count."""
    capabilities = capability_registry()
    capabilities.register("core/times_count", times_count_class())
    artifacts = artifact_registry()
    for kind in (COUNT, PERSON_COUNT):
        artifacts.register(kind.identifier, kind)
    return service(  # authored out of order on purpose
        manifest(
            selection or times_count_selection(),
            SCALE,
            inputs=frozenset({"ex/base", "ex/count"}),
        ),
        capabilities=capabilities,
        artifacts=artifacts,
    )


def test_computes_core_times_count_end_to_end() -> None:
    from tax_engine.domain.trace import TimesCountLine

    worksheet = times_count_service().compute(
        EX_ON, 2025, Artifact(BASE, D("5376.50")), Artifact(COUNT, 1)
    )["ex-on/return"][0]

    # scaled = 5376.50 × 3 = 16129.50; result = 16129.50 × 1 = 16129.50, exact.
    assert worksheet.get(SCALED).value == D("16129.50")
    assert worksheet.get(RESULT).value == D("16129.50")
    assert str(worksheet.get(RESULT).value) == "16129.50"
    assert isinstance(worksheet.producer_of(RESULT), times_count_class())
    assert worksheet.producer_of(COUNT) is None
    assert worksheet.trace[-1] == TimesCountLine(
        RESULT, SCALED, D("16129.50"), COUNT, 1, D("16129.50")
    )
    assert [type(line) for line in worksheet.trace].count(TimesCountLine) == 1


def test_computes_core_times_count_for_a_count_of_two_end_to_end() -> None:
    worksheet = times_count_service().compute(
        EX_ON, 2025, Artifact(BASE, D("5")), Artifact(COUNT, 2)
    )["ex-on/return"][0]

    # scaled = 15; result = 15 × 2 = 30.
    assert worksheet.get(RESULT).value == D("30")


def test_computes_core_times_count_for_a_count_of_zero_end_to_end() -> None:
    worksheet = times_count_service().compute(
        EX_ON, 2025, Artifact(BASE, D("5376.50")), Artifact(COUNT, 0)
    )["ex-on/return"][0]

    # A count of 0 gives a plain zero, not the amount's scale.
    assert worksheet.get(RESULT).value == D("0")
    assert str(worksheet.get(RESULT).value) == "0"


def test_core_times_count_runs_after_its_amount_is_produced() -> None:
    composition = times_count_service().compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is times_count_class()
    assert composition.order[-1].consumes == frozenset({SCALED, COUNT})


def test_core_times_count_rejects_a_money_input_for_its_count() -> None:
    built = times_count_service()

    with pytest.raises(InvalidCompositionError, match="'count' was given as Decimal but the input"):
        built.compute(
            EX_ON, 2025, Artifact(BASE, D("5")), Artifact(ArtifactKind("ex/count", Decimal), D("1"))
        )


def test_core_times_count_refuses_a_money_kind_for_its_count_at_wiring() -> None:
    built = times_count_service(times_count_selection(amount="ex/scaled", count="ex/extra"))

    with pytest.raises(InvalidSelectionError, match="core/times_count.*'count'"):
        built.compose(EX_ON, 2025)


def test_core_times_count_refuses_a_count_kind_for_its_amount_at_wiring() -> None:
    built = times_count_service(times_count_selection(amount="ex/person_count", count="ex/count"))

    with pytest.raises(InvalidSelectionError, match="core/times_count.*'amount'"):
        built.compose(EX_ON, 2025)


# --- core/choose_by_count: one of two artifacts chosen by a count, by a made-up manifest -------
#
# Like `TimesCount` above, `ChooseByCount` is imported inside a cached factory so its absence fails
# only the tests that use it, and is registered in a private registry under its shared
# identifier, `core/choose_by_count`. Its count is `ex/count`, a made-up `int` input; its first
# candidate is a produced artifact, `ex/scaled` (base × 3), and its second is `ex/extra`, a
# made-up input; it reads no dataset.


@cache
def choose_by_count_class() -> Any:
    from tax_engine.domain.capabilities.choose_by_count import ChooseByCount

    return ChooseByCount


def choose_by_count_selection(
    count: str = "ex/count", when_none: str = "ex/scaled", when_any: str = "ex/extra"
) -> CapabilitySelection:
    return CapabilitySelection(
        name="core/choose_by_count",
        params={},
        consumes={"count": count, "when_none": when_none, "when_any": when_any},
        produces={"output": "ex-on/result"},
    )


def choose_by_count_service(
    selection: CapabilitySelection | None = None,
) -> TaxComputationService:
    """`ex/scale` (base × 3) and `core/choose_by_count` producing `ex-on/result`: scaled when the
    count is 0, extra otherwise."""
    capabilities = capability_registry()
    capabilities.register("core/choose_by_count", choose_by_count_class())
    artifacts = artifact_registry()
    for kind in (COUNT, PERSON_COUNT):
        artifacts.register(kind.identifier, kind)
    return service(  # authored out of order on purpose
        manifest(
            selection or choose_by_count_selection(),
            SCALE,
            inputs=frozenset({"ex/base", "ex/extra", "ex/count"}),
        ),
        capabilities=capabilities,
        artifacts=artifacts,
    )


def test_computes_core_choose_by_count_for_a_count_of_zero_end_to_end() -> None:
    from tax_engine.domain.trace import ChosenByCountLine

    worksheet = choose_by_count_service().compute(
        EX_ON, 2025, Artifact(BASE, D("544.50")), Artifact(EXTRA, D("2813")), Artifact(COUNT, 0)
    )["ex-on/return"][0]

    # scaled = 544.50 × 3 = 1633.50; the count is 0, so result = scaled, unchanged.
    assert worksheet.get(SCALED).value == D("1633.50")
    assert worksheet.get(RESULT).value == D("1633.50")
    assert str(worksheet.get(RESULT).value) == "1633.50"
    assert isinstance(worksheet.producer_of(RESULT), choose_by_count_class())
    assert worksheet.producer_of(COUNT) is None
    assert worksheet.trace[-1] == ChosenByCountLine(RESULT, COUNT, 0, SCALED, D("1633.50"))
    assert [type(line) for line in worksheet.trace].count(ChosenByCountLine) == 1


def test_computes_core_choose_by_count_for_a_count_of_one_end_to_end() -> None:
    from tax_engine.domain.trace import ChosenByCountLine

    worksheet = choose_by_count_service().compute(
        EX_ON, 2025, Artifact(BASE, D("544.50")), Artifact(EXTRA, D("2813.00")), Artifact(COUNT, 1)
    )["ex-on/return"][0]

    # The count is 1, so result = extra 2813.00, unchanged; scaled is still produced.
    assert worksheet.get(SCALED).value == D("1633.50")
    assert worksheet.get(RESULT).value == D("2813.00")
    assert str(worksheet.get(RESULT).value) == "2813.00"
    assert worksheet.trace[-1] == ChosenByCountLine(RESULT, COUNT, 1, EXTRA, D("2813.00"))


def test_computes_core_choose_by_count_for_a_count_of_two_end_to_end() -> None:
    worksheet = choose_by_count_service().compute(
        EX_ON, 2025, Artifact(BASE, D("5")), Artifact(EXTRA, D("7")), Artifact(COUNT, 2)
    )["ex-on/return"][0]

    # The count is 2: the second candidate, as is, not twice it.
    assert worksheet.get(RESULT).value == D("7")


def test_core_choose_by_count_runs_after_its_candidates_are_produced() -> None:
    composition = choose_by_count_service().compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is choose_by_count_class()
    assert composition.order[-1].consumes == frozenset({COUNT, SCALED, EXTRA})


def test_core_choose_by_count_rejects_a_money_input_for_its_count() -> None:
    built = choose_by_count_service()

    with pytest.raises(InvalidCompositionError, match="'count' was given as Decimal but the input"):
        built.compute(
            EX_ON,
            2025,
            Artifact(BASE, D("5")),
            Artifact(EXTRA, D("7")),
            Artifact(ArtifactKind("ex/count", Decimal), D("1")),
        )


def test_core_choose_by_count_refuses_a_money_kind_for_its_count_at_wiring() -> None:
    built = choose_by_count_service(choose_by_count_selection(count="ex/base"))

    with pytest.raises(InvalidSelectionError, match="core/choose_by_count.*'count'"):
        built.compose(EX_ON, 2025)


def test_core_choose_by_count_refuses_a_count_kind_for_its_first_candidate_at_wiring() -> None:
    built = choose_by_count_service(choose_by_count_selection(when_none="ex/person_count"))

    with pytest.raises(InvalidSelectionError, match="core/choose_by_count.*'when_none'"):
        built.compose(EX_ON, 2025)


def test_core_choose_by_count_refuses_a_count_kind_for_its_second_candidate_at_wiring() -> None:
    built = choose_by_count_service(choose_by_count_selection(when_any="ex/person_count"))

    with pytest.raises(InvalidSelectionError, match="core/choose_by_count.*'when_any'"):
        built.compose(EX_ON, 2025)


# --- a record list consumed by a made-up per-item capability -----------------------------------
#
# `ex/dependants` is a made-up record-list input whose records have one field, the made-up
# `ex/dependant_net_income`. `PerItemClaim` (`ex/per_item_claim`) consumes it with two made-up
# scalar inputs, `ex/base_amount` and `ex/maximum_amount`, and does the per-item work itself: for
# each record the claim is the base less that record's net income, at least 0 and at most the
# maximum, and `ex-on/result` is the sum, with one trace line per item named by its position.
# Like `ChooseByCount` above, `RecordList` and `RecordListKind` are reached inside cached
# factories so their absence fails only the tests that use them.

DEPENDANT_NET_INCOME = ArtifactKind("ex/dependant_net_income", Decimal, non_negative=True)
BASE_AMOUNT = ArtifactKind("ex/base_amount", Decimal)
MAXIMUM_AMOUNT = ArtifactKind("ex/maximum_amount", Decimal)


@cache
def dependants_kind() -> Any:
    """The made-up `ex/dependants` record-list kind, declared like any package's."""
    from tax_engine.domain.record_list import RecordListKind

    catalog = ArtifactCatalog(Namespace("ex"))
    return RecordListKind.declare(catalog, "dependants", fields=(DEPENDANT_NET_INCOME,))


def dependants(*net_incomes: str) -> Artifact[Any]:
    """An `ex/dependants` artifact of one record per net income, in the order given."""
    from tax_engine.domain.record_list import RecordList

    kind = dependants_kind()
    records = [{DEPENDANT_NET_INCOME: D(net_income)} for net_income in net_incomes]
    return Artifact(kind, RecordList(kind.fields, records))


@cache
def per_item_claim_class() -> Any:
    from tax_engine.domain.record_list import RecordList

    class PerItemClaim(Capability):
        """Produces `total`: for each record, `base` less its net income, from 0 up to
        `maximum`, summed."""

        CONSUMES: ClassVar[Mapping[str, type]] = {
            "items": RecordList,
            "base": Decimal,
            "maximum": Decimal,
        }
        PRODUCES: ClassVar[Mapping[str, type]] = {"total": Decimal}

        def __init__(
            self, items: ArtifactKind[RecordList], base: Money, maximum: Money, total: Money
        ) -> None:
            super().__init__(items=items, base=base, maximum=maximum, total=total)
            self._items, self._base, self._maximum, self._total = items, base, maximum, total

        def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
            records = self._input(inputs, self._items).value.records
            base = self._input(inputs, self._base).value
            maximum = self._input(inputs, self._maximum).value
            total = D("0")
            trace: list[TraceLine] = []
            for position, record in enumerate(records, start=1):
                claim = min(maximum, max(D("0"), base - record[DEPENDANT_NET_INCOME]))
                trace.append(StepLine(f"item {position}", claim))
                total += claim
            trace.append(StepLine("total", total))
            return CapabilityResult(outputs=(Artifact(self._total, total),), trace=tuple(trace))

    return PerItemClaim


def per_item_claim_selection(
    items: str = "ex/dependants", base: str = "ex/base_amount"
) -> CapabilitySelection:
    return CapabilitySelection(
        name="ex/per_item_claim",
        params={},
        consumes={"items": items, "base": base, "maximum": "ex/maximum_amount"},
        produces={"total": "ex-on/result"},
    )


def per_item_claim_service(
    selection: CapabilitySelection | None = None,
) -> TaxComputationService:
    """`ex/per_item_claim` producing `ex-on/result` from the `ex/dependants` records, the base
    amount and the maximum: each record's claim from 0 up to the maximum, summed."""
    capabilities = capability_registry()
    capabilities.register("ex/per_item_claim", per_item_claim_class())
    artifacts = artifact_registry()
    for kind in (dependants_kind(), DEPENDANT_NET_INCOME, BASE_AMOUNT, MAXIMUM_AMOUNT):
        artifacts.register(kind.identifier, kind)
    return service(
        manifest(
            selection or per_item_claim_selection(),
            inputs=frozenset({"ex/dependants", "ex/base_amount", "ex/maximum_amount"}),
        ),
        capabilities=capabilities,
        artifacts=artifacts,
    )


def compute_claim(*net_incomes: str) -> Worksheet:
    return per_item_claim_service().compute(
        EX_ON,
        2025,
        dependants(*net_incomes),
        Artifact(BASE_AMOUNT, D("28798.00")),
        Artifact(MAXIMUM_AMOUNT, D("8601")),
    )["ex-on/return"][0]


def test_a_per_item_capability_over_no_records_claims_nothing() -> None:
    worksheet = compute_claim()

    assert worksheet.get(RESULT).value == D("0")
    assert worksheet.trace == (StepLine("total", D("0")),)


def test_a_per_item_capability_over_one_record() -> None:
    worksheet = compute_claim("25000")

    # 28,798.00 − 25,000 = 3,798.00, under the 8,601 maximum.
    assert worksheet.get(RESULT).value == D("3798.00")
    assert worksheet.trace == (
        StepLine("item 1", D("3798.00")),
        StepLine("total", D("3798.00")),
    )


def test_a_per_item_capability_over_three_records_differs_from_pooling_them() -> None:
    worksheet = compute_claim("5000", "25000", "20000")

    # item 1: 28,798.00 − 5,000 = 23,798.00, at most 8,601 → 8,601
    # item 2: 28,798.00 − 25,000 = 3,798.00
    # item 3: 28,798.00 − 20,000 = 8,798.00, at most 8,601 → 8,601
    # total: 8,601 + 3,798.00 + 8,601 = 21,000.00
    assert worksheet.get(RESULT).value == D("21000.00")
    assert worksheet.trace == (
        StepLine("item 1", D("8601")),
        StepLine("item 2", D("3798.00")),
        StepLine("item 3", D("8601")),
        StepLine("total", D("21000.00")),
    )
    # Pooled: 28,798.00 − (5,000 + 25,000 + 20,000) = −21,202.00, at least 0 → 0.
    pooled = min(D("8601"), max(D("0"), D("28798.00") - D("50000")))
    assert pooled == D("0")
    assert worksheet.get(RESULT).value != pooled


def test_a_per_item_capability_keeps_the_callers_record_order() -> None:
    worksheet = compute_claim("30000", "5000")

    assert [line for line in worksheet.trace if line != worksheet.trace[-1]] == [
        StepLine("item 1", D("0")),
        StepLine("item 2", D("8601")),
    ]


def test_a_record_list_is_an_ordinary_starting_artifact() -> None:
    worksheet = compute_claim("25000")

    assert worksheet.get(dependants_kind()) == dependants("25000")
    assert worksheet.producer_of(dependants_kind()) is None
    assert isinstance(worksheet.producer_of(RESULT), per_item_claim_class())


def test_a_per_item_capability_consumes_the_record_list_kind() -> None:
    composition = per_item_claim_service().compose(EX_ON, 2025).form("ex-on/return").composition

    (claim,) = composition.order
    assert claim.consumes == frozenset({dependants_kind(), BASE_AMOUNT, MAXIMUM_AMOUNT})


def test_a_per_item_capability_rejects_a_money_input_for_its_record_list() -> None:
    built = per_item_claim_service()

    with pytest.raises(
        InvalidCompositionError, match="'dependants' was given as Decimal but the input"
    ):
        built.compute(
            EX_ON,
            2025,
            Artifact(ArtifactKind("ex/dependants", Decimal), D("2")),
            Artifact(BASE_AMOUNT, D("28798.00")),
            Artifact(MAXIMUM_AMOUNT, D("8601")),
        )


def test_a_per_item_capability_refuses_a_money_kind_for_its_record_list_at_wiring() -> None:
    built = per_item_claim_service(per_item_claim_selection(items="ex/base_amount"))

    with pytest.raises(InvalidSelectionError, match="ex/per_item_claim.*'items'"):
        built.compose(EX_ON, 2025)


def test_a_per_item_capability_refuses_a_record_list_kind_for_a_money_slot_at_wiring() -> None:
    built = per_item_claim_service(
        per_item_claim_selection(items="ex/dependants", base="ex/dependants")
    )

    with pytest.raises(InvalidSelectionError, match="ex/per_item_claim"):
        built.compose(EX_ON, 2025)


# --- ca-on/choose_by_range: one of three artifacts chosen by a range, by a made-up manifest ----
#
# Like `ChooseByCount` above, `ChooseByRange` is imported inside a cached factory so its absence
# fails only the tests that use it, and is registered in a private registry under its shared
# identifier, `ca-on/choose_by_range`. Its tested amount is `ex/base`; its limits are
# `ex/first_limit` and `ex/second_limit`, made-up inputs; its first candidate is a produced
# artifact, `ex/scaled` (base × 3), its second is `ex/extra` and its third `ex/last`, made-up
# inputs; it reads no dataset.

FIRST_LIMIT = ArtifactKind("ex/first_limit", Decimal)
SECOND_LIMIT = ArtifactKind("ex/second_limit", Decimal)
LAST = ArtifactKind("ex/last", Decimal)


@cache
def choose_by_range_class() -> Any:
    from tax_engine.jurisdictions.ca_on.capabilities.choose_by_range import ChooseByRange

    return ChooseByRange


def choose_by_range_selection(
    amount: str = "ex/base",
    first: str = "ex/scaled",
    second: str = "ex/extra",
    third: str = "ex/last",
) -> CapabilitySelection:
    return CapabilitySelection(
        name="ca-on/choose_by_range",
        params={},
        consumes={
            "amount": amount,
            "first_limit": "ex/first_limit",
            "second_limit": "ex/second_limit",
            "first": first,
            "second": second,
            "third": third,
        },
        produces={"output": "ex-on/result"},
    )


def choose_by_range_service(
    selection: CapabilitySelection | None = None,
) -> TaxComputationService:
    """`ex/scale` (base × 3) and `ca-on/choose_by_range` producing `ex-on/result`: scaled when the
    base is at most the first limit, extra when it is over that but at most the second limit, last
    otherwise."""
    capabilities = capability_registry()
    capabilities.register("ca-on/choose_by_range", choose_by_range_class())
    artifacts = artifact_registry()
    for kind in (FIRST_LIMIT, SECOND_LIMIT, LAST, PERSON_COUNT):
        artifacts.register(kind.identifier, kind)
    return service(  # authored out of order on purpose
        manifest(
            selection or choose_by_range_selection(),
            SCALE,
            inputs=frozenset(
                {"ex/base", "ex/extra", "ex/last", "ex/first_limit", "ex/second_limit"}
            ),
        ),
        capabilities=capabilities,
        artifacts=artifacts,
    )


def compute_choose_by_range(base: str) -> Worksheet:
    return choose_by_range_service().compute(
        EX_ON,
        2025,
        Artifact(BASE, D(base)),
        Artifact(EXTRA, D("20.00")),
        Artifact(LAST, D("30.00")),
        Artifact(FIRST_LIMIT, D("100")),
        Artifact(SECOND_LIMIT, D("200")),
    )["ex-on/return"][0]


def test_computes_ca_on_choose_by_range_for_the_first_range_end_to_end() -> None:
    from tax_engine.domain.trace import ChosenByRangeLine

    worksheet = compute_choose_by_range("30")

    # scaled = 30 × 3 = 90; 30 is at most the first limit of 100, so result = scaled, unchanged.
    assert worksheet.get(SCALED).value == D("90")
    assert worksheet.get(RESULT).value == D("90")
    assert isinstance(worksheet.producer_of(RESULT), choose_by_range_class())
    assert worksheet.producer_of(BASE) is None
    assert worksheet.producer_of(FIRST_LIMIT) is None
    assert worksheet.trace[-1] == ChosenByRangeLine(RESULT, BASE, D("30"), SCALED, D("90"))
    assert [type(line) for line in worksheet.trace].count(ChosenByRangeLine) == 1


def test_computes_ca_on_choose_by_range_for_the_second_range_end_to_end() -> None:
    from tax_engine.domain.trace import ChosenByRangeLine

    worksheet = compute_choose_by_range("150")

    # 150 is more than 100 but at most 200, so result = extra 20.00, unchanged; scaled is still
    # produced.
    assert worksheet.get(SCALED).value == D("450")
    assert worksheet.get(RESULT).value == D("20.00")
    assert str(worksheet.get(RESULT).value) == "20.00"
    assert worksheet.trace[-1] == ChosenByRangeLine(RESULT, BASE, D("150"), EXTRA, D("20.00"))


def test_computes_ca_on_choose_by_range_for_the_third_range_end_to_end() -> None:
    worksheet = compute_choose_by_range("250")

    assert worksheet.get(RESULT).value == D("30.00")


def test_computes_ca_on_choose_by_range_on_each_limit_end_to_end() -> None:
    assert compute_choose_by_range("100").get(RESULT).value == D("300")
    assert compute_choose_by_range("200").get(RESULT).value == D("20.00")
    assert compute_choose_by_range("200.01").get(RESULT).value == D("30.00")


def test_ca_on_choose_by_range_runs_after_its_candidates_and_limits_are_produced() -> None:
    composition = choose_by_range_service().compose(EX_ON, 2025).form("ex-on/return").composition

    assert type(composition.order[-1]) is choose_by_range_class()
    assert composition.order[-1].consumes == frozenset(
        {BASE, FIRST_LIMIT, SECOND_LIMIT, SCALED, EXTRA, LAST}
    )


def test_ca_on_choose_by_range_refuses_a_count_kind_for_its_amount_at_wiring() -> None:
    built = choose_by_range_service(choose_by_range_selection(amount="ex/person_count"))

    with pytest.raises(InvalidSelectionError, match="ca-on/choose_by_range.*'amount'"):
        built.compose(EX_ON, 2025)


def test_ca_on_choose_by_range_refuses_a_count_kind_for_its_first_candidate_at_wiring() -> None:
    built = choose_by_range_service(choose_by_range_selection(first="ex/person_count"))

    with pytest.raises(InvalidSelectionError, match="ca-on/choose_by_range.*'first'"):
        built.compose(EX_ON, 2025)


def test_ca_on_choose_by_range_refuses_a_count_kind_for_its_third_candidate_at_wiring() -> None:
    built = choose_by_range_service(choose_by_range_selection(third="ex/person_count"))

    with pytest.raises(InvalidSelectionError, match="ca-on/choose_by_range.*'third'"):
        built.compose(EX_ON, 2025)


def test_an_input_that_is_also_an_output_is_carried_onto_the_worksheet_as_entered() -> None:
    carried = manifest(
        inputs=frozenset({"ex/base", "ex/extra"}),
        outputs=frozenset({"ex-on/result", "ex/extra"}),
    )
    entered = Artifact(EXTRA, D("12.50"))

    worksheet = service(carried).compute(EX_ON, 2025, Artifact(BASE, D("5")), entered)[
        "ex-on/return"
    ][0]

    assert worksheet.get(EXTRA) == entered
    assert worksheet.producer_of(EXTRA) is None
    assert worksheet.get(RESULT).value == D("16")


# `ex/business_number` is a made-up digits input of nine digits that the default manifest also
# returns, so it is carried onto the return as entered: nothing computes it and nothing has to
# consume it. Like `RecordListKind` above, `DigitsKind` is reached inside a cached factory so its
# absence fails only the tests that use it.
@cache
def business_number_kind() -> Any:
    """The made-up `ex/business_number` digits kind of nine digits, declared like any package's."""
    from tax_engine.domain.digits import DigitsKind

    return DigitsKind.declare(ArtifactCatalog(Namespace("ex")), "business_number", digits=9)


def business_number_service() -> TaxComputationService:
    """The default manifest, also carrying `ex/business_number` onto the return as entered."""
    artifacts = artifact_registry()
    artifacts.register(business_number_kind().identifier, business_number_kind())
    return service(
        manifest(
            inputs=frozenset({"ex/base", "ex/business_number"}),
            outputs=frozenset({"ex-on/result", "ex/business_number"}),
        ),
        artifacts=artifacts,
    )


@pytest.mark.parametrize("text", ["012345678", ""])
def test_a_carried_digits_entry_is_returned_as_entered(text: str) -> None:
    entered = Artifact(business_number_kind(), text)

    worksheet = business_number_service().compute(EX_ON, 2025, Artifact(BASE, D("5")), entered)[
        "ex-on/return"
    ][0]

    assert worksheet.get(business_number_kind()) == entered
    assert worksheet.producer_of(business_number_kind()) is None
    assert worksheet.get(RESULT).value == D("16")


def test_a_digits_kind_of_another_number_of_digits_is_not_the_carried_entry() -> None:
    from tax_engine.domain.digits import DigitsKind

    other = DigitsKind("ex/business_number", digits=5)

    with pytest.raises(InvalidCompositionError, match="'business_number'"):
        business_number_service().compute(
            EX_ON, 2025, Artifact(BASE, D("5")), Artifact(other, "12345")
        )["ex-on/return"][0]
