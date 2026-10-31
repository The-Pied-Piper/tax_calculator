"""Unit tests for the RatioTruncated capability (`ca/ratio_truncated`), with made-up kinds.

A ratio of two money figures, rounded once by a `rounding_only` dataset (a form line such as
"line 4 divided by line 5, calculated to the fifth decimal place without rounding" is the dataset
with increment 0.00001 and mode down). Its slots: one parameter slot `rounding` (a `rounding_only`
dataset), two consumed slots `dividend` and `divisor` (`Decimal` kinds), one produced slot
`output`, a `Rate` kind. Two capabilities share one implementation and these slots:
`ca/ratio_truncated` (`RatioTruncated`) and `ca/ratio_truncated_at_most_one`
(`RatioTruncatedAtMostOne`), both in the module `ratio_truncated`.

The output is `rounding.apply(dividend / divisor)`, the quotient an exact fraction. A zero divisor
gives 0, never an error. The `at_most_one` one: a dividend above the divisor gives 1, checked
before the zero-divisor rule (a positive dividend over a zero divisor gives 1), else the rounded
ratio. Each records one `RatioTruncatedLine`, its `cap_at_one` field set by which class
records it.

The output is a `Rate`: a ratio above 1 from the uncapped one (and any negative ratio) raises
`InvalidRateError` from `Rate` itself.

Worked example: 30,000 / 70,000 = 0.428571..., down to 0.00001 is 0.42857.
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
    InvalidRateError,
    MissingArtifactError,
    NotFoundError,
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
from tax_engine.domain.trace import RatioTruncatedLine
from tax_engine.jurisdictions.ca.capabilities.ratio_truncated import (
    RatioTruncated,
    RatioTruncatedAtMostOne,
)
from tests.manifest_support import required_inputs

D = Decimal
FIVE_DECIMALS_DOWN = RoundTo(D("0.00001"), RoundingMode.DOWN)

DIVIDEND = ArtifactKind("ex/part_earned", Decimal)
DIVISOR = ArtifactKind("ex/all_earned", Decimal)
OUTPUT = ArtifactKind("ex/earned_share", Rate)


def rounding(rule: RoundingRule = FIVE_DECIMALS_DOWN) -> ParameterDataset[RoundingOnly]:
    return ParameterDataset(
        "ex/share_rounding", 2025, ROUNDING_ONLY, RoundingOnly(), rule, ("https://example.org/r",)
    )


def capability(
    data: ParameterDataset[RoundingOnly] | None = None, cap_at_one: bool = False
) -> RatioTruncated | RatioTruncatedAtMostOne:
    cls = RatioTruncatedAtMostOne if cap_at_one else RatioTruncated
    return cls(data or rounding(), DIVIDEND, DIVISOR, OUTPUT)


def inputs(dividend: str, divisor: str) -> tuple[Artifact[Any], ...]:
    return (Artifact(DIVIDEND, D(dividend)), Artifact(DIVISOR, D(divisor)))


def compute(
    wired: RatioTruncated | RatioTruncatedAtMostOne, dividend: str, divisor: str
) -> Artifact[Any]:
    (output,) = wired.compute(inputs(dividend, divisor)).outputs
    return output


def test_is_registered_as_ca_ratio_truncated() -> None:
    assert CapabilityRegistry.shared().get("ca/ratio_truncated") is RatioTruncated


def test_the_capped_one_is_registered_as_ca_ratio_truncated_at_most_one() -> None:
    registry = CapabilityRegistry.shared()

    assert registry.get("ca/ratio_truncated_at_most_one") is RatioTruncatedAtMostOne
    assert RatioTruncatedAtMostOne is not RatioTruncated


def test_is_exported_from_the_federal_capabilities_package() -> None:
    assert "ratio_truncated" in ca_capabilities.__all__
    assert ca_capabilities.ratio_truncated.RatioTruncated is RatioTruncated


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({DIVIDEND, DIVISOR})
    assert capability().produces == frozenset({OUTPUT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(RatioTruncated)
    assert "produces" not in vars(RatioTruncated)


def test_declares_its_slots() -> None:
    assert RatioTruncated.PARAMETERS == {"rounding": ROUNDING_ONLY}
    assert RatioTruncated.PARAMETERS["rounding"] is ROUNDING_ONLY
    assert RatioTruncated.CONSUMES == {"dividend": Decimal, "divisor": Decimal}
    assert RatioTruncated.PRODUCES == {"output": Rate}
    assert not RatioTruncated.is_list_slot("dividend")
    assert not RatioTruncated.is_list_slot("divisor")


def test_the_capped_one_has_the_same_slots_and_no_flag() -> None:
    for cls in (RatioTruncated, RatioTruncatedAtMostOne):
        assert cls.PARAMETERS == {"rounding": ROUNDING_ONLY}
        assert cls.CONSUMES == {"dividend": Decimal, "divisor": Decimal}
        assert cls.PRODUCES == {"output": Rate}


def test_takes_no_flag() -> None:
    with pytest.raises(TypeError):
        RatioTruncated(rounding(), DIVIDEND, DIVISOR, OUTPUT, cap_at_one=True)  # type: ignore[call-arg]


def test_its_slots_are_read_only() -> None:
    for slots in (RatioTruncated.PARAMETERS, RatioTruncated.CONSUMES, RatioTruncated.PRODUCES):
        assert isinstance(slots, MappingProxyType)


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(RatioTruncated.PARAMETERS, Mapping[str, ParameterKind[RoundingOnly]])
    assert_type(RatioTruncated.CONSUMES, Mapping[str, type])
    assert_type(RatioTruncated.PRODUCES, Mapping[str, type])


def test_its_slots_cannot_be_changed() -> None:
    for slots in (RatioTruncated.PARAMETERS, RatioTruncated.CONSUMES, RatioTruncated.PRODUCES):
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = RatioTruncated(rounding=rounding(), dividend=DIVIDEND, divisor=DIVISOR, output=OUTPUT)

    assert compute(wired, "30000", "70000") == Artifact(OUTPUT, Rate(D("0.42857")))


def test_the_capped_one_is_built_from_its_slot_names_as_keywords() -> None:
    wired = RatioTruncatedAtMostOne(
        rounding=rounding(), dividend=DIVIDEND, divisor=DIVISOR, output=OUTPUT
    )

    assert compute(wired, "3", "2") == Artifact(OUTPUT, Rate(D("1")))


@pytest.mark.parametrize(
    ("kinds", "slots"),
    [
        ((DIVIDEND, DIVIDEND, OUTPUT), ("'dividend'", "'divisor'")),
    ],
)
def test_rejects_one_kind_in_two_slots(
    kinds: tuple[ArtifactKind[Any], ArtifactKind[Any], ArtifactKind[Any]],
    slots: tuple[str, str],
) -> None:
    with pytest.raises(InvalidCapabilityError, match="RatioTruncated") as raised:
        RatioTruncated(rounding(), *kinds)

    for slot in slots:
        assert slot in str(raised.value)


@pytest.mark.parametrize("money", [DIVIDEND, DIVISOR])
def test_rejects_a_money_kind_for_its_rate_output(money: ArtifactKind[Decimal]) -> None:
    # The output slot takes a Rate kind, so a money kind (also one already used) is refused.
    with pytest.raises(InvalidCapabilityError, match="RatioTruncated.*'output'.*Rate"):
        RatioTruncated(rounding(), DIVIDEND, DIVISOR, money)  # type: ignore[arg-type]


def test_rejects_a_list_of_kinds_for_its_dividend() -> None:
    with pytest.raises(InvalidCapabilityError, match="RatioTruncated.*'dividend'"):
        RatioTruncated(rounding(), (DIVIDEND,), DIVISOR, OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_wiring_a_count_kind_for_the_divisor() -> None:
    count = ArtifactKind("ex/count", int)
    # The ignore fails under mypy (warn_unused_ignores) if an ArtifactKind[int] is ever accepted
    # as money. At run time, building it fails too.
    with pytest.raises(InvalidCapabilityError, match="RatioTruncated.*'divisor'"):
        RatioTruncated(rounding(), DIVIDEND, count, OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        other = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.1")), NO_ROUNDING, ("https://e.org",)
        )
        RatioTruncated(other, DIVIDEND, DIVISOR, OUTPUT)  # type: ignore[arg-type]

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(RatioTruncated, "__type_params__", ())
    assert not getattr(RatioTruncated, "__parameters__", ())


# --- computing: the ratio -----------------------------------------------------------------------


def test_a_rounding_only_dataset_of_increment_0_00001_mode_down_truncates_the_ratio() -> None:
    # 30,000 / 70,000 = 0.4285714285..., the worked example's line 6.
    output = compute(capability(), "30000", "70000")

    assert output == Artifact(OUTPUT, Rate(D("0.42857")))
    assert type(output.value) is Rate


def test_truncates_toward_zero_rather_than_rounding() -> None:
    # 2/3 = 0.666666...: half up to five decimals would give 0.66667.
    assert compute(capability(), "2", "3") == Artifact(OUTPUT, Rate(D("0.66666")))


def test_the_ratio_is_exact_not_a_float_or_a_28_digit_decimal() -> None:
    # 1,000,000 / 999,999 = 1.000001000001...
    assert compute(capability(), "1000000", "999999") == Artifact(OUTPUT, Rate(D("1.00000")))
    assert compute(capability(), "999999", "1000000") == Artifact(OUTPUT, Rate(D("0.99999")))


def test_a_ratio_with_a_finite_expansion_is_kept_exactly() -> None:
    assert compute(capability(), "1", "8") == Artifact(OUTPUT, Rate(D("0.12500")))


def test_a_zero_dividend_gives_zero() -> None:
    assert compute(capability(), "0", "70000") == Artifact(OUTPUT, Rate(D("0")))


def test_a_dividend_above_the_divisor_is_not_a_rate_by_default() -> None:
    # 70,000 / 30,000 = 2.33333 is no rate: Rate refuses it. A negative dividend or divisor gives a
    # negative ratio, refused the same way.
    with pytest.raises(InvalidRateError):
        capability().compute(inputs("70000", "30000"))
    with pytest.raises(InvalidRateError):
        capability().compute(inputs("-1", "2"))


def test_a_dividend_equal_to_the_divisor_gives_one() -> None:
    assert compute(capability(), "70000", "70000") == Artifact(OUTPUT, Rate(D("1")))


def test_the_output_carries_the_increments_scale() -> None:
    assert str(compute(capability(), "1", "2").value.value) == "0.50000"


def test_rounds_with_another_rule_of_the_dataset() -> None:
    wired = capability(rounding(RoundTo(D("0.01"), RoundingMode.HALF_UP)))

    assert compute(wired, "2", "3") == Artifact(OUTPUT, Rate(D("0.67")))


def test_an_inexact_ratio_under_no_rounding_raises_inexact() -> None:
    with pytest.raises(decimal.Inexact):
        capability(rounding(NO_ROUNDING)).compute(inputs("1", "3"))


def test_an_exact_ratio_under_no_rounding_is_kept_exactly() -> None:
    assert compute(capability(rounding(NO_ROUNDING)), "1", "4") == Artifact(OUTPUT, Rate(D("0.25")))


# --- computing: a zero divisor ------------------------------------------------------------------


def test_a_zero_divisor_gives_zero_not_an_error() -> None:
    output = compute(capability(), "30000", "0")

    assert output == Artifact(OUTPUT, Rate(D("0")))
    assert type(output.value) is Rate


def test_a_zero_dividend_over_a_zero_divisor_gives_zero() -> None:
    assert compute(capability(), "0", "0") == Artifact(OUTPUT, Rate(D("0")))


def test_a_zero_divisor_gives_zero_under_no_rounding() -> None:
    assert compute(capability(rounding(NO_ROUNDING)), "5", "0") == Artifact(OUTPUT, Rate(D("0")))


# --- computing: the at-most-one capability ---------------------------------------------------


def test_with_cap_at_one_a_dividend_above_the_divisor_gives_exactly_one() -> None:
    output = compute(capability(cap_at_one=True), "70000", "30000")

    assert output == Artifact(OUTPUT, Rate(D("1")))
    assert type(output.value) is Rate


def test_with_cap_at_one_a_dividend_below_the_divisor_gives_the_truncated_ratio() -> None:
    assert compute(capability(cap_at_one=True), "30000", "70000") == Artifact(
        OUTPUT, Rate(D("0.42857"))
    )


def test_with_cap_at_one_a_dividend_equal_to_the_divisor_gives_one() -> None:
    assert compute(capability(cap_at_one=True), "70000", "70000") == Artifact(OUTPUT, Rate(D("1")))


def test_with_cap_at_one_a_positive_dividend_over_a_zero_divisor_gives_one() -> None:
    # The cap is checked before the zero-divisor rule.
    assert compute(capability(cap_at_one=True), "5", "0") == Artifact(OUTPUT, Rate(D("1")))


def test_with_cap_at_one_a_zero_dividend_over_a_zero_divisor_gives_zero() -> None:
    assert compute(capability(cap_at_one=True), "0", "0") == Artifact(OUTPUT, Rate(D("0")))


def test_with_cap_at_one_a_zero_dividend_gives_zero() -> None:
    assert compute(capability(cap_at_one=True), "0", "70000") == Artifact(OUTPUT, Rate(D("0")))


def test_without_cap_at_one_a_positive_dividend_over_a_zero_divisor_gives_zero() -> None:
    assert compute(capability(cap_at_one=False), "5", "0") == Artifact(OUTPUT, Rate(D("0")))


def test_cap_at_one_does_not_change_a_ratio_below_one() -> None:
    plain = compute(capability(), "2", "3")

    assert compute(capability(cap_at_one=True), "2", "3") == plain


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("9"))

    result = capability().compute((other, *inputs("1", "2")))

    assert result.outputs == (Artifact(OUTPUT, Rate(D("0.5"))),)


def test_a_missing_dividend_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="part_earned"):
        capability().compute((Artifact(DIVISOR, D("1")),))


def test_a_missing_divisor_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="all_earned"):
        capability().compute((Artifact(DIVIDEND, D("1")),))


def test_has_one_output() -> None:
    assert len(capability().compute(inputs("1", "2")).outputs) == 1


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(inputs("1", "3")) == wired.compute(inputs("1", "3"))


# --- trace --------------------------------------------------------------------------------------


def test_traces_one_ratio_truncated_line() -> None:
    trace = capability().compute(inputs("30000", "70000")).trace

    assert trace == (
        RatioTruncatedLine(
            output=OUTPUT,
            dividend=DIVIDEND,
            dividend_amount=D("30000"),
            divisor=DIVISOR,
            divisor_amount=D("70000"),
            rounding=FIVE_DECIMALS_DOWN,
            cap_at_one=False,
            result=D("0.42857"),
        ),
    )


def test_traces_the_cap_flag_and_the_capped_result() -> None:
    trace = capability(cap_at_one=True).compute(inputs("70000", "30000")).trace

    assert trace == (
        RatioTruncatedLine(
            OUTPUT,
            DIVIDEND,
            D("70000"),
            DIVISOR,
            D("30000"),
            FIVE_DECIMALS_DOWN,
            True,
            D("1"),
        ),
    )


def test_traces_a_zero_divisor_with_a_zero_result() -> None:
    (line,) = capability().compute(inputs("5", "0")).trace

    assert isinstance(line, RatioTruncatedLine)
    assert line.divisor_amount == D("0")
    assert line.result == D("0")


def test_trace_amount_is_the_result() -> None:
    trace = capability().compute(inputs("30000", "70000")).trace

    assert [line.amount for line in trace] == [D("0.42857")]


def test_trace_result_is_the_output() -> None:
    result = capability().compute(inputs("30000", "70000"))

    (line,) = result.trace
    (output,) = result.outputs
    assert isinstance(line, RatioTruncatedLine)
    assert Rate(line.result) == output.value


def test_trace_holds_no_text() -> None:
    for line in capability().compute(inputs("1", "3")).trace:
        assert not any(isinstance(getattr(line, f.name), str) for f in fields(line))


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[RoundingOnly]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, ROUNDING_ONLY):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(dataset: ParameterDataset[RoundingOnly] | None = None) -> TaxComputationService:
    dataset = dataset or rounding()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/ratio_truncated",
        params={"rounding": dataset.family},
        consumes={"dividend": "ex/part_earned", "divisor": "ex/all_earned"},
        produces={"output": "ex/earned_share"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/part_earned", "ex/all_earned"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/earned_share",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (DIVIDEND, DIVISOR, OUTPUT):
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
    assert isinstance(built, RatioTruncated)
    assert built.consumes == frozenset({DIVIDEND, DIVISOR})
    assert built.produces == frozenset({OUTPUT})


def test_a_computation_truncates_the_ratio_to_five_decimals() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *inputs("30000", "70000"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OUTPUT).value == Rate(D("0.42857"))
    assert isinstance(worksheet.producer_of(OUTPUT), RatioTruncated)


def test_a_computation_with_an_inexact_ratio_and_no_rounding_names_the_capability() -> None:
    built = service(rounding(NO_ROUNDING))

    with pytest.raises(CapabilityContractError, match=r"RatioTruncated .*inexact") as raised:
        built.compute(JurisdictionCode("CA-ON"), 2025, *inputs("1", "3"))

    assert isinstance(raised.value.__cause__, decimal.Inexact)
