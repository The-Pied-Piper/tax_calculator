"""Unit tests for the SignChosenDifference capability (`ca/sign_chosen_difference`).

Uses made-up `ex/` kinds and figures.

T691 Part 1 line 23: "If line 20 is positive, enter the amount from line 22. If line 20 is negative,
enter whichever is less: the amount from line 21 or line 22 (show in brackets)." Line 22 is "Line 20
minus line 21 (if negative, do not show in brackets.)".

It picks by the sign of one consumed figure. Its slots: no parameter slots, consumed slots
`sign_amount`, `reference` and `difference`, and one produced slot `output`. When `sign_amount`
is zero or positive, the output is `difference` as it is. When `sign_amount` is negative, the
output is the lesser of `reference` and the magnitude of `difference`, as a negative number, so
the output is signed. It never rounds: the output is one of the consumed figures, or its negative.
It records one `SignChosenDifferenceLine`.
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
from tax_engine.domain.errors import InvalidCapabilityError, MissingArtifactError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.trace import SignChosenDifferenceLine
from tax_engine.jurisdictions.ca.capabilities.sign_chosen_difference import SignChosenDifference
from tests.manifest_support import required_inputs

D = Decimal

SIGN = ArtifactKind("ex/sign_amount", Decimal)
REFERENCE = ArtifactKind("ex/reference", Decimal)
DIFFERENCE = ArtifactKind("ex/difference", Decimal)
OUTPUT = ArtifactKind("ex/out", Decimal)


def capability() -> SignChosenDifference:
    return SignChosenDifference(SIGN, REFERENCE, DIFFERENCE, OUTPUT)


def inputs(sign: str, reference: str, difference: str) -> tuple[Artifact[Any], ...]:
    return (
        Artifact(SIGN, D(sign)),
        Artifact(REFERENCE, D(reference)),
        Artifact(DIFFERENCE, D(difference)),
    )


def compute(sign: str, reference: str, difference: str) -> Artifact[Any]:
    (output,) = capability().compute(inputs(sign, reference, difference)).outputs
    return output


def test_is_registered_as_ca_sign_chosen_difference() -> None:
    assert CapabilityRegistry.shared().get("ca/sign_chosen_difference") is SignChosenDifference


def test_is_exported_from_the_federal_capabilities_package() -> None:
    assert "sign_chosen_difference" in ca_capabilities.__all__
    assert ca_capabilities.sign_chosen_difference.SignChosenDifference is SignChosenDifference


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({SIGN, REFERENCE, DIFFERENCE})
    assert capability().produces == frozenset({OUTPUT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(SignChosenDifference)
    assert "produces" not in vars(SignChosenDifference)


def test_declares_its_slots() -> None:
    assert SignChosenDifference.PARAMETERS == {}
    assert SignChosenDifference.CONSUMES == {
        "sign_amount": Decimal,
        "reference": Decimal,
        "difference": Decimal,
    }
    assert SignChosenDifference.PRODUCES == {"output": Decimal}
    assert not SignChosenDifference.is_list_slot("sign_amount")
    assert not SignChosenDifference.is_list_slot("reference")
    assert not SignChosenDifference.is_list_slot("difference")


def test_its_slots_are_read_only() -> None:
    slot_maps = (
        SignChosenDifference.PARAMETERS,
        SignChosenDifference.CONSUMES,
        SignChosenDifference.PRODUCES,
    )
    for slots in slot_maps:
        assert isinstance(slots, MappingProxyType)


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(SignChosenDifference.PARAMETERS, Mapping[str, ParameterKind[Any]])
    assert_type(SignChosenDifference.CONSUMES, Mapping[str, type])
    assert_type(SignChosenDifference.PRODUCES, Mapping[str, type])


def test_its_slots_cannot_be_changed() -> None:
    slot_maps = (
        SignChosenDifference.PARAMETERS,
        SignChosenDifference.CONSUMES,
        SignChosenDifference.PRODUCES,
    )
    for slots in slot_maps:
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = SignChosenDifference(
        sign_amount=SIGN, reference=REFERENCE, difference=DIFFERENCE, output=OUTPUT
    )

    (output,) = wired.compute(inputs("100", "30", "70")).outputs

    assert output == Artifact(OUTPUT, D("70"))


def test_takes_no_parameter_dataset() -> None:
    with pytest.raises(TypeError):
        SignChosenDifference(  # type: ignore[call-arg]
            cast(Any, object()), SIGN, REFERENCE, DIFFERENCE, OUTPUT
        )


def test_rejects_one_kind_as_both_sign_amount_and_reference() -> None:
    with pytest.raises(InvalidCapabilityError, match="SignChosenDifference") as raised:
        SignChosenDifference(SIGN, SIGN, DIFFERENCE, OUTPUT)

    message = str(raised.value)
    assert "'sign_amount'" in message
    assert "'reference'" in message


def test_rejects_one_kind_as_both_reference_and_difference() -> None:
    with pytest.raises(InvalidCapabilityError, match="SignChosenDifference") as raised:
        SignChosenDifference(SIGN, REFERENCE, REFERENCE, OUTPUT)

    message = str(raised.value)
    assert "'reference'" in message
    assert "'difference'" in message


def test_rejects_one_kind_as_both_sign_amount_and_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="SignChosenDifference") as raised:
        SignChosenDifference(SIGN, REFERENCE, DIFFERENCE, SIGN)

    message = str(raised.value)
    assert "'sign_amount'" in message
    assert "'output'" in message


def test_rejects_a_list_of_kinds_for_its_reference() -> None:
    with pytest.raises(InvalidCapabilityError, match="SignChosenDifference.*'reference'"):
        SignChosenDifference(SIGN, (REFERENCE,), DIFFERENCE, OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_wiring_an_artifact_kind_of_another_value_type() -> None:
    count = ArtifactKind("ex/count", int)
    # An ArtifactKind[int] is not Money; the ignore fails under mypy (warn_unused_ignores) if
    # wiring an artifact kind of another value type is ever accepted. At run time, building it
    # fails too.
    with pytest.raises(InvalidCapabilityError, match="SignChosenDifference.*'sign_amount'"):
        SignChosenDifference(count, REFERENCE, DIFFERENCE, OUTPUT)  # type: ignore[arg-type]


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(SignChosenDifference, "__type_params__", ())
    assert not getattr(SignChosenDifference, "__parameters__", ())


# --- computing: a positive sign amount ------------------------------------------------------------


def test_a_positive_sign_amount_gives_the_difference_as_it_is() -> None:
    assert compute("100", "30", "70") == Artifact(OUTPUT, D("70"))


def test_a_positive_sign_amount_ignores_a_smaller_reference() -> None:
    # The reference is only compared when the sign amount is negative.
    assert compute("100", "5", "95").value == D("95")


def test_a_positive_sign_amount_ignores_a_larger_reference() -> None:
    assert compute("100", "500", "-400").value == D("-400")


def test_a_positive_result_stays_positive() -> None:
    assert compute("0.01", "0", "0.01").value == D("0.01")


# --- computing: a zero sign amount ----------------------------------------------------------------


def test_a_zero_sign_amount_with_a_zero_reference_gives_zero() -> None:
    output = compute("0", "0", "0")

    assert output == Artifact(OUTPUT, D("0"))


def test_a_zero_sign_amount_gives_the_difference_as_it_is() -> None:
    # Zero is not negative: the difference is taken as it is, whatever the reference.
    assert compute("0", "5", "-5").value == D("-5")


def test_a_zero_sign_amount_with_a_positive_difference_gives_the_difference() -> None:
    assert compute("0", "0", "12.5").value == D("12.5")


# --- computing: a negative sign amount ------------------------------------------------------------


def test_a_negative_sign_amount_gives_the_lesser_figure_negated() -> None:
    # Line 20 -100, line 21 30, line 22 130 (without brackets): the lesser, 30, in brackets.
    assert compute("-100", "30", "130").value == D("-30")


def test_a_negative_sign_amount_with_a_smaller_difference_gives_the_difference() -> None:
    assert compute("-10", "50", "20").value == D("-20")


def test_a_negative_sign_amount_with_a_larger_reference_gives_the_difference_negated() -> None:
    # Line 20 -100, line 21 500, line 22 600: lesser of 500 and 600 is 500.
    assert compute("-100", "500", "600").value == D("-500")


def test_a_negative_sign_amount_takes_the_magnitude_of_a_signed_difference() -> None:
    # The difference may arrive signed (line 20 minus line 21 is -130); its magnitude is compared.
    assert compute("-100", "30", "-130").value == D("-30")


def test_a_negative_sign_amount_with_a_signed_difference_below_the_reference() -> None:
    assert compute("-10", "50", "-20").value == D("-20")


def test_a_negative_sign_amount_with_equal_reference_and_difference() -> None:
    assert compute("-100", "40", "40").value == D("-40")


def test_a_negative_sign_amount_with_a_zero_reference_gives_zero() -> None:
    assert compute("-100", "0", "100").value == D("0")


def test_a_negative_sign_amount_with_a_zero_difference_gives_zero() -> None:
    assert compute("-100", "100", "0").value == D("0")


def test_a_negative_result_is_below_zero() -> None:
    assert compute("-100", "30", "130").value < D("0")


def test_the_smallest_negative_sign_amount_is_negative() -> None:
    assert compute("-0.01", "0.01", "0.02").value == D("-0.01")


def test_the_result_is_exact_not_rounded() -> None:
    assert compute("-100", "30.005", "130.005").value == D("-30.005")


def test_a_positive_difference_is_never_made_negative_by_a_non_negative_sign_amount() -> None:
    assert compute("1", "1", "2").value == D("2")


# --- computing: inputs ----------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("9"))

    result = capability().compute((other, *inputs("100", "30", "70")))

    assert result.outputs == (Artifact(OUTPUT, D("70")),)


def test_the_order_of_the_inputs_does_not_matter() -> None:
    forward = capability().compute(inputs("-100", "30", "130"))
    backward = capability().compute(tuple(reversed(inputs("-100", "30", "130"))))

    assert forward == backward


@pytest.mark.parametrize("missing", ["sign_amount", "reference", "difference"])
def test_a_missing_input_is_a_missing_artifact(missing: str) -> None:
    kept = tuple(a for a in inputs("100", "30", "70") if not a.kind.identifier.endswith(missing))

    with pytest.raises(MissingArtifactError, match=missing):
        capability().compute(kept)


def test_with_no_inputs_it_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError):
        capability().compute(())


def test_has_one_output() -> None:
    assert len(capability().compute(inputs("100", "30", "70")).outputs) == 1


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(inputs("-100", "30", "130")) == wired.compute(inputs("-100", "30", "130"))


# --- trace ----------------------------------------------------------------------------------------


def test_traces_one_sign_chosen_difference_line_for_a_positive_sign_amount() -> None:
    trace = capability().compute(inputs("100", "30", "70")).trace

    assert trace == (
        SignChosenDifferenceLine(
            output=OUTPUT,
            sign=SIGN,
            sign_amount=D("100"),
            reference=REFERENCE,
            reference_amount=D("30"),
            difference=DIFFERENCE,
            difference_amount=D("70"),
            result=D("70"),
        ),
    )


def test_traces_one_sign_chosen_difference_line_for_a_negative_sign_amount() -> None:
    trace = capability().compute(inputs("-100", "30", "130")).trace

    assert trace == (
        SignChosenDifferenceLine(
            OUTPUT, SIGN, D("-100"), REFERENCE, D("30"), DIFFERENCE, D("130"), D("-30")
        ),
    )


def test_traces_one_sign_chosen_difference_line_for_a_zero_sign_amount() -> None:
    trace = capability().compute(inputs("0", "0", "0")).trace

    assert trace == (
        SignChosenDifferenceLine(
            OUTPUT, SIGN, D("0"), REFERENCE, D("0"), DIFFERENCE, D("0"), D("0")
        ),
    )


def test_trace_amount_is_the_result() -> None:
    trace = capability().compute(inputs("-100", "30", "130")).trace

    assert [line.amount for line in trace] == [D("-30")]


def test_trace_result_is_the_output() -> None:
    result = capability().compute(inputs("-100", "500", "600"))

    (line,) = result.trace
    (output,) = result.outputs
    assert isinstance(line, SignChosenDifferenceLine)
    assert line.result == output.value


def test_trace_holds_no_text() -> None:
    trace = capability().compute(inputs("-100", "30", "130")).trace

    for line in trace:
        assert not any(isinstance(getattr(line, f.name), str) for f in fields(line))


# --- through TaxComputationService ----------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> Any:
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service() -> TaxComputationService:
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/sign_chosen_difference",
        params={},
        consumes={
            "sign_amount": "ex/sign_amount",
            "reference": "ex/reference",
            "difference": "ex/difference",
        },
        produces={"output": "ex/out"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/sign_amount", "ex/reference", "ex/difference"})),
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
    for kind in (SIGN, REFERENCE, DIFFERENCE, OUTPUT):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, SignChosenDifference)
    assert built.consumes == frozenset({SIGN, REFERENCE, DIFFERENCE})
    assert built.produces == frozenset({OUTPUT})


def test_a_computation_picks_by_the_sign_amount() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *inputs("-100", "30", "130"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OUTPUT).value == D("-30")
    assert isinstance(worksheet.producer_of(OUTPUT), SignChosenDifference)
    assert worksheet.trace == (
        SignChosenDifferenceLine(
            OUTPUT, SIGN, D("-100"), REFERENCE, D("30"), DIFFERENCE, D("130"), D("-30")
        ),
    )
