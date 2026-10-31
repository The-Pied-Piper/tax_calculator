"""Unit tests for the LesserOfWithMaximum capability (`ca/lesser_of_with_maximum`).

Uses made-up `ex/` kinds and figures.

Form T1436 line 9 (Line 25300, "if you have pre-1986 capital loss balance"): "Enter whichever is
less: amount from line 3, line 8, or $2,000." (confirmed from the PDF; no .txt published).

It is the "whichever is less" of `core/lesser_of` with a dataset figure among the candidates, as
`core/capped_amount` has for one base. Its slots: one parameter slot `maximum` (an `amount`
dataset), one consumed list slot `amounts` (at least one kind) and one produced slot `output`.
The output is the least of the amounts' values and the maximum's value: at or below the maximum
the least amount is produced as it is (keeping its scale, the first listed winning a tie); above
it, the maximum's value. The result is rounded only with the dataset's rule. It records one
`LesserOfWithMaximumLine` holding the amounts in the order they were wired, the maximum, the
rounding rule and the result.
"""

from __future__ import annotations

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
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.amount import AMOUNT, Amount
from tax_engine.domain.parameters.credit import CREDIT, Credit
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)
from tax_engine.domain.trace import LesserOfWithMaximumLine
from tax_engine.jurisdictions.ca.capabilities.lesser_of_with_maximum import LesserOfWithMaximum
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)

PART_ONE = ArtifactKind("ex/part_one", Decimal)
PART_TWO = ArtifactKind("ex/part_two", Decimal)
PART_THREE = ArtifactKind("ex/part_three", Decimal)
OUTPUT = ArtifactKind("ex/out", Decimal)


def maximum(value: str = "2000", rounding: RoundingRule = NO_ROUNDING) -> ParameterDataset[Amount]:
    """By default the form's $2,000, as printed, with no rounding."""
    return ParameterDataset(
        "ex/some_maximum", 2025, AMOUNT, Amount(D(value)), rounding, ("https://example.org/m",)
    )


def capability(
    data: ParameterDataset[Amount] | None = None,
    amounts: tuple[ArtifactKind[Decimal], ...] = (PART_ONE, PART_TWO),
) -> LesserOfWithMaximum:
    return LesserOfWithMaximum(data or maximum(), amounts, OUTPUT)


def inputs(*values: tuple[ArtifactKind[Decimal], str]) -> tuple[Artifact[Any], ...]:
    return tuple(Artifact(kind, D(value)) for kind, value in values)


def compute(wired: LesserOfWithMaximum, one: str, two: str) -> Artifact[Any]:
    (output,) = wired.compute(inputs((PART_ONE, one), (PART_TWO, two))).outputs
    return output


def test_is_registered_as_ca_lesser_of_with_maximum() -> None:
    assert CapabilityRegistry.shared().get("ca/lesser_of_with_maximum") is LesserOfWithMaximum


def test_is_exported_from_the_federal_capabilities_package() -> None:
    assert "lesser_of_with_maximum" in ca_capabilities.__all__
    assert ca_capabilities.lesser_of_with_maximum.LesserOfWithMaximum is LesserOfWithMaximum


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({PART_ONE, PART_TWO})
    assert capability().produces == frozenset({OUTPUT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(LesserOfWithMaximum)
    assert "produces" not in vars(LesserOfWithMaximum)


def test_declares_its_slots() -> None:
    assert LesserOfWithMaximum.PARAMETERS == {"maximum": AMOUNT}
    assert LesserOfWithMaximum.PARAMETERS["maximum"] is AMOUNT
    assert LesserOfWithMaximum.CONSUMES == {"amounts": list[Decimal]}
    assert LesserOfWithMaximum.PRODUCES == {"output": Decimal}
    assert LesserOfWithMaximum.is_list_slot("amounts")


def test_its_slots_are_read_only() -> None:
    for slots in (
        LesserOfWithMaximum.PARAMETERS,
        LesserOfWithMaximum.CONSUMES,
        LesserOfWithMaximum.PRODUCES,
    ):
        assert isinstance(slots, MappingProxyType)


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(LesserOfWithMaximum.PARAMETERS, Mapping[str, ParameterKind[Amount]])
    assert_type(LesserOfWithMaximum.CONSUMES, Mapping[str, type])
    assert_type(LesserOfWithMaximum.PRODUCES, Mapping[str, type])


def test_its_slots_cannot_be_changed() -> None:
    for slots in (
        LesserOfWithMaximum.PARAMETERS,
        LesserOfWithMaximum.CONSUMES,
        LesserOfWithMaximum.PRODUCES,
    ):
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = LesserOfWithMaximum(maximum=maximum(), amounts=(PART_ONE, PART_TWO), output=OUTPUT)

    assert compute(wired, "150", "80") == Artifact(OUTPUT, D("80"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        LesserOfWithMaximum(maximum(), (PART_ONE,), OUTPUT, CENT)  # type: ignore[call-arg]


def test_rejects_an_empty_list_of_amounts() -> None:
    with pytest.raises(InvalidCapabilityError, match="LesserOfWithMaximum.*'amounts'"):
        LesserOfWithMaximum(maximum(), (), OUTPUT)


def test_rejects_one_kind_as_both_an_amount_and_the_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="LesserOfWithMaximum") as raised:
        LesserOfWithMaximum(maximum(), (PART_ONE, OUTPUT), OUTPUT)

    message = str(raised.value)
    assert "'amounts'" in message
    assert "'output'" in message


def test_rejects_an_amount_listed_twice() -> None:
    with pytest.raises(InvalidCapabilityError, match="LesserOfWithMaximum.*'amounts'"):
        LesserOfWithMaximum(maximum(), (PART_ONE, PART_TWO, PART_ONE), OUTPUT)


def test_rejects_a_single_kind_for_its_amounts() -> None:
    with pytest.raises(InvalidCapabilityError, match="LesserOfWithMaximum.*'amounts'"):
        LesserOfWithMaximum(maximum(), PART_ONE, OUTPUT)  # type: ignore[arg-type]


def test_rejects_an_amount_of_another_value_type() -> None:
    count = ArtifactKind("ex/count", int)

    with pytest.raises(InvalidCapabilityError, match="LesserOfWithMaximum.*'amounts'"):
        LesserOfWithMaximum(maximum(), (PART_ONE, count), OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        # A credit dataset is not a ParameterDataset[Amount]; the ignore fails under mypy
        # (warn_unused_ignores) if it is ever accepted.
        credit = ParameterDataset(
            "ex/some_credit", 2025, CREDIT, Credit(D("1")), NO_ROUNDING, ("https://example.org/c",)
        )
        LesserOfWithMaximum(credit, (PART_ONE,), OUTPUT)  # type: ignore[arg-type]

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(LesserOfWithMaximum, "__type_params__", ())
    assert not getattr(LesserOfWithMaximum, "__parameters__", ())


# --- computing ----------------------------------------------------------------------------------


def test_produces_the_first_amount_when_it_is_the_least() -> None:
    output = compute(capability(), "80", "150")

    assert output == Artifact(OUTPUT, D("80"))
    assert type(output.value) is Decimal


def test_produces_the_second_amount_when_it_is_the_least() -> None:
    assert compute(capability(), "150", "80") == Artifact(OUTPUT, D("80"))


def test_produces_the_maximum_when_both_amounts_are_above_it() -> None:
    # Line 9 is $2,000 when line 3 and line 8 are both over it.
    assert compute(capability(), "2500", "3000") == Artifact(OUTPUT, D("2000"))


def test_produces_the_maximum_when_one_amount_is_just_above_it() -> None:
    assert compute(capability(), "2000.01", "5000") == Artifact(OUTPUT, D("2000"))


def test_an_amount_equal_to_the_maximum_is_produced_keeping_its_scale() -> None:
    output = compute(capability(), "2000.00", "5000")

    assert output == Artifact(OUTPUT, D("2000"))
    assert str(output.value) == "2000.00"


def test_the_maximum_comes_from_the_dataset() -> None:
    assert compute(capability(maximum("500")), "800", "900") == Artifact(OUTPUT, D("500"))
    assert compute(capability(maximum("500")), "300", "900") == Artifact(OUTPUT, D("300"))


def test_the_maximum_is_taken_as_printed_not_rounded_without_a_rule() -> None:
    output = compute(capability(maximum("2000")), "3000", "4000")

    assert str(output.value) == "2000"


def test_produces_the_least_of_three_amounts() -> None:
    wired = capability(amounts=(PART_ONE, PART_TWO, PART_THREE))

    (output,) = wired.compute(
        inputs((PART_ONE, "900"), (PART_TWO, "700.50"), (PART_THREE, "800"))
    ).outputs

    assert output == Artifact(OUTPUT, D("700.50"))


def test_the_order_of_the_inputs_does_not_matter() -> None:
    forward = capability().compute(inputs((PART_ONE, "150"), (PART_TWO, "80")))
    backward = capability().compute(inputs((PART_TWO, "80"), (PART_ONE, "150")))

    assert forward.outputs == backward.outputs == (Artifact(OUTPUT, D("80")),)


def test_one_amount_is_its_own_lesser_below_the_maximum() -> None:
    wired = capability(amounts=(PART_ONE,))

    (output,) = wired.compute(inputs((PART_ONE, "1234.56"))).outputs

    assert output == Artifact(OUTPUT, D("1234.56"))


def test_one_amount_above_the_maximum_produces_the_maximum() -> None:
    wired = capability(amounts=(PART_ONE,))

    (output,) = wired.compute(inputs((PART_ONE, "2000.01"))).outputs

    assert output == Artifact(OUTPUT, D("2000"))


def test_equal_amounts_produce_the_first_listed_keeping_its_scale() -> None:
    output = compute(capability(), "80.00", "80")

    assert output == Artifact(OUTPUT, D("80"))
    assert str(output.value) == "80.00"


def test_a_zero_amount_produces_zero() -> None:
    # Line 9 is 0 when line 3 is 0 (lines 1 to 3 not completed).
    output = compute(capability(), "0", "1500")

    assert output == Artifact(OUTPUT, D("0"))
    assert type(output.value) is Decimal


def test_keeps_the_lesser_exact_without_rounding() -> None:
    assert compute(capability(), "0.123456789012345678901234567890", "5") == Artifact(
        OUTPUT, D("0.123456789012345678901234567890")
    )


def test_rounds_the_lesser_with_the_datasets_rule() -> None:
    wired = capability(maximum("2000", CENT))

    assert compute(wired, "80.005", "150") == Artifact(OUTPUT, D("80.01"))


def test_rounds_the_maximum_with_the_datasets_rule() -> None:
    wired = capability(maximum("1999.995", CENT))

    assert compute(wired, "2500", "3000") == Artifact(OUTPUT, D("2000.00"))


def test_a_negative_amount_is_the_lesser() -> None:
    assert compute(capability(), "-50", "20") == Artifact(OUTPUT, D("-50"))


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("1"))

    result = capability().compute((other, *inputs((PART_ONE, "150"), (PART_TWO, "80"))))

    assert result.outputs == (Artifact(OUTPUT, D("80")),)


def test_a_missing_amount_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="part_two"):
        capability().compute(inputs((PART_ONE, "150")))


def test_has_one_output() -> None:
    assert len(capability().compute(inputs((PART_ONE, "1"), (PART_TWO, "2"))).outputs) == 1


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = inputs((PART_ONE, "2500"), (PART_TWO, "3000"))

    assert wired.compute(given) == wired.compute(given)


# --- trace --------------------------------------------------------------------------------------


def test_traces_one_line_with_each_amount_the_maximum_and_the_result() -> None:
    trace = capability().compute(inputs((PART_ONE, "150"), (PART_TWO, "80"))).trace

    assert trace == (
        LesserOfWithMaximumLine(
            output=OUTPUT,
            parts=((PART_ONE, D("150")), (PART_TWO, D("80"))),
            maximum=Amount(D("2000")),
            rounding=NO_ROUNDING,
            result=D("80"),
        ),
    )


def test_traces_the_maximum_as_the_result_when_it_is_the_least() -> None:
    trace = capability().compute(inputs((PART_ONE, "2500"), (PART_TWO, "3000"))).trace

    assert trace == (
        LesserOfWithMaximumLine(
            OUTPUT,
            ((PART_ONE, D("2500")), (PART_TWO, D("3000"))),
            Amount(D("2000")),
            NO_ROUNDING,
            D("2000"),
        ),
    )


def test_traces_the_amounts_in_the_order_they_were_wired() -> None:
    wired = capability(amounts=(PART_TWO, PART_ONE))

    (line,) = wired.compute(inputs((PART_ONE, "150"), (PART_TWO, "80"))).trace

    assert isinstance(line, LesserOfWithMaximumLine)
    assert line.parts == ((PART_TWO, D("80")), (PART_ONE, D("150")))


def test_traces_the_datasets_rounding_rule_and_the_rounded_result() -> None:
    trace = (
        capability(maximum("2000", CENT))
        .compute(inputs((PART_ONE, "80.005"), (PART_TWO, "150")))
        .trace
    )

    assert trace == (
        LesserOfWithMaximumLine(
            OUTPUT,
            ((PART_ONE, D("80.005")), (PART_TWO, D("150"))),
            Amount(D("2000")),
            CENT,
            D("80.01"),
        ),
    )


def test_trace_amount_is_the_result() -> None:
    trace = capability().compute(inputs((PART_ONE, "150"), (PART_TWO, "80"))).trace

    assert [line.amount for line in trace] == [D("80")]


def test_trace_result_is_the_output() -> None:
    result = capability().compute(inputs((PART_ONE, "2500"), (PART_TWO, "3000")))

    (line,) = result.trace
    (output,) = result.outputs
    assert isinstance(line, LesserOfWithMaximumLine)
    assert line.result == output.value


def test_trace_holds_no_text() -> None:
    trace = capability().compute(inputs((PART_ONE, "150"), (PART_TWO, "80"))).trace

    for line in trace:
        assert not any(isinstance(getattr(line, f.name), str) for f in fields(line))


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[Amount]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, AMOUNT):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(dataset: ParameterDataset[Amount] | None = None) -> TaxComputationService:
    dataset = dataset or maximum()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/lesser_of_with_maximum",
        params={"maximum": dataset.family},
        consumes={"amounts": ("ex/part_one", "ex/part_two")},
        produces={"output": "ex/out"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/part_one", "ex/part_two"})),
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
    for kind in (PART_ONE, PART_TWO, OUTPUT):
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
    assert isinstance(built, LesserOfWithMaximum)
    assert built.consumes == frozenset({PART_ONE, PART_TWO})
    assert built.produces == frozenset({OUTPUT})


def test_a_computation_caps_the_lesser_at_the_datasets_maximum() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, *inputs((PART_ONE, "2500"), (PART_TWO, "3000"))
    )["ca-on/return"][0]

    assert worksheet.get(OUTPUT).value == D("2000")
    assert isinstance(worksheet.producer_of(OUTPUT), LesserOfWithMaximum)
    assert worksheet.trace == (
        LesserOfWithMaximumLine(
            OUTPUT,
            ((PART_ONE, D("2500")), (PART_TWO, D("3000"))),
            Amount(D("2000")),
            NO_ROUNDING,
            D("2000"),
        ),
    )


def test_a_computation_produces_the_lesser_amount_below_the_maximum() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, *inputs((PART_ONE, "1500"), (PART_TWO, "700"))
    )["ca-on/return"][0]

    assert worksheet.get(OUTPUT).value == D("700")
