"""Unit tests for the DividedByRate capability (`ca/divided_by_rate`).

Uses made-up `ex/` kinds and figures.

T1206 Part 2 ("TOSI-adjusted taxable income ... Amount from line 8 ÷ 14.5% = 8A") and Part 3
lines 33A to 33C ("Amount from line 33A divided by the tax rate you entered on line 33B").

It mirrors `core/apply_rate`, but divides. Its slots: one parameter slot `rate` (a `rate`
dataset), one consumed slot `dividend` and one produced slot `output`. The output is the consumed
`dividend` divided by the dataset's rate as an exact fraction (5.05% divides as 2,000/101),
rounded once by the dataset's rounding rule; under `rounding: none` an inexact division raises
`decimal.Inexact`. It records one `DividedByRateLine`.
"""

from __future__ import annotations

import decimal
from collections.abc import Mapping
from dataclasses import fields
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    CapabilityContractError,
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.credit import CREDIT, Credit
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)
from tax_engine.domain.trace import DividedByRateLine
from tax_engine.jurisdictions.ca.capabilities.divided_by_rate import DividedByRate
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)

DIVIDEND = ArtifactKind("ex/dividend", Decimal)
OUTPUT = ArtifactKind("ex/out", Decimal)


def rate(value: str = "0.145", rounding: RoundingRule = CENT) -> ParameterDataset[Rate]:
    """By default the federal figures: 14.5%, to the cent."""
    return ParameterDataset(
        "ex/divisor_rate", 2025, RATE, Rate(D(value)), rounding, ("https://example.org/r",)
    )


def capability(rate_data: ParameterDataset[Rate] | None = None) -> DividedByRate:
    return DividedByRate(rate_data or rate(), DIVIDEND, OUTPUT)


def inputs(dividend: str) -> tuple[Artifact[Any], ...]:
    return (Artifact(DIVIDEND, D(dividend)),)


def compute(wired: DividedByRate, dividend: str) -> Artifact[Any]:
    (output,) = wired.compute(inputs(dividend)).outputs
    return output


def test_is_registered_as_ca_divided_by_rate() -> None:
    assert CapabilityRegistry.shared().get("ca/divided_by_rate") is DividedByRate


def test_is_exported_from_the_federal_capabilities_package() -> None:
    assert "divided_by_rate" in ca_capabilities.__all__
    assert ca_capabilities.divided_by_rate.DividedByRate is DividedByRate


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({DIVIDEND})
    assert capability().produces == frozenset({OUTPUT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(DividedByRate)
    assert "produces" not in vars(DividedByRate)


def test_declares_its_slots() -> None:
    assert DividedByRate.PARAMETERS == {"rate": RATE}
    assert DividedByRate.PARAMETERS["rate"] is RATE
    assert DividedByRate.CONSUMES == {"dividend": Decimal}
    assert DividedByRate.PRODUCES == {"output": Decimal}
    assert not DividedByRate.is_list_slot("dividend")


def test_its_slots_are_read_only() -> None:
    for slots in (DividedByRate.PARAMETERS, DividedByRate.CONSUMES, DividedByRate.PRODUCES):
        assert isinstance(slots, MappingProxyType)


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(DividedByRate.PARAMETERS, Mapping[str, ParameterKind[Rate]])
    assert_type(DividedByRate.CONSUMES, Mapping[str, type])
    assert_type(DividedByRate.PRODUCES, Mapping[str, type])


def test_its_slots_cannot_be_changed() -> None:
    for slots in (DividedByRate.PARAMETERS, DividedByRate.CONSUMES, DividedByRate.PRODUCES):
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = DividedByRate(rate=rate(), dividend=DIVIDEND, output=OUTPUT)

    assert compute(wired, "3795") == Artifact(OUTPUT, D("26172.41"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        DividedByRate(rate(), DIVIDEND, OUTPUT, CENT)  # type: ignore[call-arg]


def test_rejects_one_kind_as_both_dividend_and_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="DividedByRate") as raised:
        DividedByRate(rate(), DIVIDEND, DIVIDEND)

    message = str(raised.value)
    assert "'dividend'" in message
    assert "'output'" in message


def test_rejects_a_list_of_kinds_for_its_dividend() -> None:
    with pytest.raises(InvalidCapabilityError, match="DividedByRate.*'dividend'"):
        DividedByRate(rate(), (DIVIDEND,), OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_wiring_an_artifact_kind_of_another_value_type() -> None:
    count = ArtifactKind("ex/count", int)
    # An ArtifactKind[int] is not Money; the ignore fails under mypy (warn_unused_ignores) if
    # wiring an artifact kind of another value type is ever accepted. At run time, building it
    # fails too.
    with pytest.raises(InvalidCapabilityError, match="DividedByRate.*'dividend'"):
        DividedByRate(rate(), count, OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        # A credit dataset is not a ParameterDataset[Rate]; the ignore fails under mypy
        # (warn_unused_ignores) if it is ever accepted.
        credit = ParameterDataset(
            "ex/some_credit", 2025, CREDIT, Credit(D("1")), NO_ROUNDING, ("https://example.org/c",)
        )
        DividedByRate(credit, DIVIDEND, OUTPUT)  # type: ignore[arg-type]

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(DividedByRate, "__type_params__", ())
    assert not getattr(DividedByRate, "__parameters__", ())


# --- computing ----------------------------------------------------------------------------------


def test_divides_the_dividend_by_the_rate_half_up_to_the_cent() -> None:
    # 3,795 / 14.5% = 26,172.4137..., T1206 line 8A.
    output = compute(capability(), "3795")

    assert output == Artifact(OUTPUT, D("26172.41"))
    assert type(output.value) is Decimal


def test_divides_by_five_point_zero_five_percent() -> None:
    # 2,360.95 / 5.05% = 46,751.4851..., T1206 line 33C.
    assert compute(capability(rate("0.0505")), "2360.95") == Artifact(OUTPUT, D("46751.49"))


def test_the_rate_comes_from_the_dataset() -> None:
    assert compute(capability(rate("0.5")), "100") == Artifact(OUTPUT, D("200"))


def test_the_division_is_exact_not_a_float_or_a_28_digit_decimal() -> None:
    # 1 / 0.3 = 3.3333...; 5.05% divides as 2,000/101: 2,360.95 / 0.0505 = 46751.48514851...
    thirds = capability(rate("0.3", RoundTo(D("0.0001"), RoundingMode.DOWN)))
    exact = capability(rate("0.0505", RoundTo(D("0.0001"), RoundingMode.DOWN)))

    assert compute(thirds, "1") == Artifact(OUTPUT, D("3.3333"))
    assert compute(exact, "2360.95") == Artifact(OUTPUT, D("46751.4851"))


def test_divides_exactly_with_many_decimals() -> None:
    wired = capability(rate("0.3", NO_ROUNDING))

    output = compute(wired, "0.3000000000000000000000000003")

    assert output == Artifact(OUTPUT, D("1.000000000000000000000000001"))
    assert type(output.value) is Decimal


def test_a_zero_dividend_produces_zero() -> None:
    output = compute(capability(), "0")

    assert output == Artifact(OUTPUT, D("0"))
    assert type(output.value) is Decimal


def test_a_rate_of_one_produces_the_dividend() -> None:
    assert compute(capability(rate("1")), "1234.56") == Artifact(OUTPUT, D("1234.56"))


def test_a_negative_dividend_produces_a_negative_quotient() -> None:
    assert compute(capability(rate("0.5")), "-100") == Artifact(OUTPUT, D("-200"))


# --- computing: rounding ------------------------------------------------------------------------


def test_the_division_is_rounded_once_half_up() -> None:
    # 0.0025 / 0.5 = 0.005 exactly: half up gives 0.01 (half even would give 0.00).
    assert compute(capability(rate("0.5")), "0.0025") == Artifact(OUTPUT, D("0.01"))


def test_a_quotient_just_under_the_half_cent_rounds_down() -> None:
    assert compute(capability(rate("0.5")), "0.00249") == Artifact(OUTPUT, D("0.00"))


def test_rounds_with_another_rule_of_the_rate_dataset() -> None:
    wired = capability(rate("0.145", RoundTo(D("1"), RoundingMode.FLOOR)))

    assert compute(wired, "3795") == Artifact(OUTPUT, D("26172"))


def test_a_rounded_output_carries_the_increments_scale() -> None:
    assert str(compute(capability(rate("0.5")), "14").value) == "28.00"


def test_an_exact_division_under_no_rounding_is_kept_exactly() -> None:
    # 5.05 / 5.05% = 100.
    assert compute(capability(rate("0.0505", NO_ROUNDING)), "5.05") == Artifact(OUTPUT, D("100"))


def test_an_inexact_division_under_no_rounding_raises_inexact() -> None:
    # 3,795 / 14.5% has no finite decimal expansion.
    with pytest.raises(decimal.Inexact):
        capability(rate("0.145", NO_ROUNDING)).compute(inputs("3795"))


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("9"))

    result = capability(rate("0.5")).compute((other, *inputs("10")))

    assert result.outputs == (Artifact(OUTPUT, D("20")),)


def test_a_missing_dividend_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="dividend"):
        capability().compute(())


def test_has_one_output() -> None:
    assert len(capability().compute(inputs("3795")).outputs) == 1


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(inputs("3795")) == wired.compute(inputs("3795"))


# --- trace --------------------------------------------------------------------------------------


def test_traces_one_divided_by_rate_line() -> None:
    trace = capability().compute(inputs("3795")).trace

    assert trace == (
        DividedByRateLine(
            output=OUTPUT,
            dividend=DIVIDEND,
            dividend_amount=D("3795"),
            rate=Rate(D("0.145")),
            rounding=CENT,
            result=D("26172.41"),
        ),
    )


def test_traces_the_rate_datasets_rounding_rule_and_the_rounded_result() -> None:
    trace = capability(rate("0.0505", NO_ROUNDING)).compute(inputs("5.05")).trace

    assert trace == (
        DividedByRateLine(OUTPUT, DIVIDEND, D("5.05"), Rate(D("0.0505")), NO_ROUNDING, D("100")),
    )


def test_trace_amount_is_the_result() -> None:
    trace = capability().compute(inputs("3795")).trace

    assert [line.amount for line in trace] == [D("26172.41")]


def test_trace_result_is_the_output() -> None:
    result = capability().compute(inputs("3795"))

    (line,) = result.trace
    (output,) = result.outputs
    assert isinstance(line, DividedByRateLine)
    assert line.result == output.value


def test_trace_holds_no_text() -> None:
    trace = capability().compute(inputs("3795")).trace

    for line in trace:
        assert not any(isinstance(getattr(line, f.name), str) for f in fields(line))


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[Rate]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, RATE):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(dataset: ParameterDataset[Rate] | None = None) -> TaxComputationService:
    dataset = dataset or rate()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/divided_by_rate",
        params={"rate": dataset.family},
        consumes={"dividend": "ex/dividend"},
        produces={"output": "ex/out"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/dividend"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/out",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (DIVIDEND, OUTPUT):
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
    assert isinstance(built, DividedByRate)
    assert built.consumes == frozenset({DIVIDEND})
    assert built.produces == frozenset({OUTPUT})


def test_a_computation_divides_by_the_datasets_rate() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *inputs("3795"))["ca-on/return"][
        0
    ]

    assert worksheet.get(OUTPUT).value == D("26172.41")
    assert isinstance(worksheet.producer_of(OUTPUT), DividedByRate)
    assert worksheet.trace == (
        DividedByRateLine(OUTPUT, DIVIDEND, D("3795"), Rate(D("0.145")), CENT, D("26172.41")),
    )


def test_a_computation_with_an_inexact_division_and_no_rounding_names_the_capability() -> None:
    built = service(rate("0.145", NO_ROUNDING))

    with pytest.raises(CapabilityContractError, match=r"DividedByRate .*inexact") as raised:
        built.compute(JurisdictionCode("CA-ON"), 2025, *inputs("3795"))

    assert isinstance(raised.value.__cause__, decimal.Inexact)
