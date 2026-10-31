"""Unit tests for the AmountOrDividedByRate capability (`ca/amount_or_divided_by_rate`).

Uses made-up `ex/` kinds and figures.

Schedule 11 line 11: "Enter the amount from line 26000 of your return on line 11 if it is
$57,375 or less. If it is more than $57,375, enter the result of the following calculation: Amount
from line 76 of your return divided by 14.5% =". Schedule ON(S11) line 2 reads the same way with
$52,886 and 5.05%.

Its slots: one parameter slot `limit` (a `threshold_rate` dataset: the threshold, the rate and the
rounding rule), two consumed slots `amount` (the figure tested against the threshold) and
`dividend` (the figure divided) and one produced slot `output`. At or below the threshold ("or
less") the output is `amount`; over it, `dividend` divided by the rate. The division is an exact
fraction, so 5.05% divides as 2,000/101, and the dataset's rounding rule rounds the chosen figure
once. Under `rounding: none` an inexact division raises `decimal.Inexact`. It records one
`AmountOrDividedByRateLine`.
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
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)
from tax_engine.domain.parameters.threshold_rate import THRESHOLD_RATE, ThresholdRate
from tax_engine.domain.trace import AmountOrDividedByRateLine
from tax_engine.jurisdictions.ca.capabilities.amount_or_divided_by_rate import (
    AmountOrDividedByRate,
)
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)

AMOUNT = ArtifactKind("ex/amount", Decimal)
DIVIDEND = ArtifactKind("ex/dividend", Decimal)
OUTPUT = ArtifactKind("ex/out", Decimal)


def limit(
    threshold: str = "52886", rate: str = "0.0505", rounding: RoundingRule = CENT
) -> ParameterDataset[ThresholdRate]:
    """By default the Ontario figures: 52,886 and 5.05%, to the cent."""
    return ParameterDataset(
        "ex/amount_limit",
        2025,
        THRESHOLD_RATE,
        ThresholdRate(Rate(D(rate)), D(threshold)),
        rounding,
        ("https://example.org/limit",),
    )


def capability(dataset: ParameterDataset[ThresholdRate] | None = None) -> AmountOrDividedByRate:
    return AmountOrDividedByRate(dataset or limit(), AMOUNT, DIVIDEND, OUTPUT)


def inputs(amount: str, dividend: str) -> tuple[Artifact[Any], ...]:
    return (Artifact(AMOUNT, D(amount)), Artifact(DIVIDEND, D(dividend)))


def compute(wired: AmountOrDividedByRate, amount: str, dividend: str) -> Artifact[Any]:
    (output,) = wired.compute(inputs(amount, dividend)).outputs
    return output


def test_is_registered_as_ca_amount_or_divided_by_rate() -> None:
    assert CapabilityRegistry.shared().get("ca/amount_or_divided_by_rate") is AmountOrDividedByRate


def test_is_exported_from_the_federal_capabilities_package() -> None:
    assert "amount_or_divided_by_rate" in ca_capabilities.__all__
    assert ca_capabilities.amount_or_divided_by_rate.AmountOrDividedByRate is AmountOrDividedByRate


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({AMOUNT, DIVIDEND})
    assert capability().produces == frozenset({OUTPUT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(AmountOrDividedByRate)
    assert "produces" not in vars(AmountOrDividedByRate)


def test_declares_its_slots() -> None:
    assert AmountOrDividedByRate.PARAMETERS == {"limit": THRESHOLD_RATE}
    assert AmountOrDividedByRate.PARAMETERS["limit"] is THRESHOLD_RATE
    assert AmountOrDividedByRate.CONSUMES == {"amount": Decimal, "dividend": Decimal}
    assert AmountOrDividedByRate.PRODUCES == {"output": Decimal}
    assert not AmountOrDividedByRate.is_list_slot("amount")
    assert not AmountOrDividedByRate.is_list_slot("dividend")


def test_its_slots_are_read_only() -> None:
    for slots in (
        AmountOrDividedByRate.PARAMETERS,
        AmountOrDividedByRate.CONSUMES,
        AmountOrDividedByRate.PRODUCES,
    ):
        assert isinstance(slots, MappingProxyType)


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(AmountOrDividedByRate.PARAMETERS, Mapping[str, ParameterKind[ThresholdRate]])
    assert_type(AmountOrDividedByRate.CONSUMES, Mapping[str, type])
    assert_type(AmountOrDividedByRate.PRODUCES, Mapping[str, type])


def test_its_slots_cannot_be_changed() -> None:
    for slots in (
        AmountOrDividedByRate.PARAMETERS,
        AmountOrDividedByRate.CONSUMES,
        AmountOrDividedByRate.PRODUCES,
    ):
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = AmountOrDividedByRate(limit=limit(), amount=AMOUNT, dividend=DIVIDEND, output=OUTPUT)

    assert compute(wired, "50000", "3321.67") == Artifact(OUTPUT, D("50000"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        AmountOrDividedByRate(limit(), AMOUNT, DIVIDEND, OUTPUT, CENT)  # type: ignore[call-arg]


def test_rejects_one_kind_as_both_amount_and_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="AmountOrDividedByRate") as raised:
        AmountOrDividedByRate(limit(), AMOUNT, DIVIDEND, AMOUNT)

    message = str(raised.value)
    assert "'amount'" in message
    assert "'output'" in message


def test_rejects_one_kind_as_both_dividend_and_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="AmountOrDividedByRate") as raised:
        AmountOrDividedByRate(limit(), AMOUNT, DIVIDEND, DIVIDEND)

    message = str(raised.value)
    assert "'dividend'" in message
    assert "'output'" in message


def test_rejects_one_kind_for_both_the_amount_and_the_dividend() -> None:
    with pytest.raises(
        InvalidCapabilityError, match="AmountOrDividedByRate.*'amount' and 'dividend'"
    ):
        AmountOrDividedByRate(limit(), AMOUNT, AMOUNT, OUTPUT)


def test_rejects_a_list_of_kinds_for_its_amount() -> None:
    with pytest.raises(InvalidCapabilityError, match="AmountOrDividedByRate.*'amount'"):
        AmountOrDividedByRate(
            limit(),
            (AMOUNT,),  # type: ignore[arg-type]
            DIVIDEND,
            OUTPUT,
        )


def test_mypy_rejects_wiring_a_dividend_kind_of_another_value_type() -> None:
    count = ArtifactKind("ex/count", int)
    # An ArtifactKind[int] is not Money; the ignore fails under mypy (warn_unused_ignores) if
    # wiring an artifact kind of another value type is ever accepted. At run time, building it
    # fails too.
    with pytest.raises(InvalidCapabilityError, match="AmountOrDividedByRate.*'dividend'"):
        AmountOrDividedByRate(limit(), AMOUNT, count, OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        # A rate dataset is not a ParameterDataset[ThresholdRate]; the ignore fails under mypy
        # (warn_unused_ignores) if it is ever accepted.
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        AmountOrDividedByRate(rate, AMOUNT, DIVIDEND, OUTPUT)  # type: ignore[arg-type]

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(AmountOrDividedByRate, "__type_params__", ())
    assert not getattr(AmountOrDividedByRate, "__parameters__", ())


# --- computing: at or below the threshold -------------------------------------------------------


def test_an_amount_below_the_threshold_passes_through() -> None:
    output = compute(capability(), "50000", "3321.67")

    assert output == Artifact(OUTPUT, D("50000"))
    assert type(output.value) is Decimal


def test_an_amount_exactly_at_the_threshold_passes_through() -> None:
    # "if it is $52,886 or less".
    assert compute(capability(), "52886", "3321.67") == Artifact(OUTPUT, D("52886"))


def test_a_zero_amount_passes_through_as_zero() -> None:
    assert compute(capability(), "0", "0") == Artifact(OUTPUT, D("0"))


def test_a_negative_amount_is_at_or_below_the_threshold() -> None:
    assert compute(capability(), "-100", "3321.67") == Artifact(OUTPUT, D("-100"))


def test_the_dividend_does_not_matter_at_or_below_the_threshold() -> None:
    assert compute(capability(), "50000", "0") == Artifact(OUTPUT, D("50000"))
    assert compute(capability(), "50000", "999999") == Artifact(OUTPUT, D("50000"))


# --- computing: over the threshold --------------------------------------------------------------


def test_an_amount_over_the_threshold_gives_the_dividend_divided_by_the_rate() -> None:
    # ON428 line 8 of 3,321.67 / 5.05% = 65,775.6435..., half up to the cent.
    assert compute(capability(), "60000", "3321.67") == Artifact(OUTPUT, D("65775.64"))


def test_the_federal_figures_divide_by_14_5_percent() -> None:
    dataset = limit(threshold="57375", rate="0.145")

    # 10,907.51 / 14.5% = 75,224.2137..., half up to the cent.
    assert compute(capability(dataset), "70000", "10907.51") == Artifact(OUTPUT, D("75224.21"))


def test_the_federal_threshold_passes_70000_through_only_up_to_57375() -> None:
    dataset = limit(threshold="57375", rate="0.145")

    assert compute(capability(dataset), "57375", "10907.51") == Artifact(OUTPUT, D("57375"))
    assert compute(capability(dataset), "57375.01", "10907.51") == Artifact(OUTPUT, D("75224.21"))


def test_a_cent_over_the_threshold_divides() -> None:
    assert compute(capability(), "52886.01", "3321.67") == Artifact(OUTPUT, D("65775.64"))


def test_the_amount_over_the_threshold_does_not_reach_the_output() -> None:
    assert compute(capability(), "60000", "3321.67") != Artifact(OUTPUT, D("60000"))
    assert compute(capability(), "1000000", "3321.67") == compute(capability(), "60000", "3321.67")


def test_a_zero_dividend_over_the_threshold_gives_zero() -> None:
    assert compute(capability(), "60000", "0") == Artifact(OUTPUT, D("0"))


def test_the_division_is_exact_not_a_float_or_a_28_digit_decimal() -> None:
    # 5.05% divides as 2,000/101; 3,321.67 / 0.0505 = 65775.64356435643564...
    wired = capability(limit(rounding=RoundTo(D("0.0001"), RoundingMode.DOWN)))

    assert compute(wired, "60000", "3321.67") == Artifact(OUTPUT, D("65775.6435"))


def test_the_threshold_comes_from_the_dataset() -> None:
    assert compute(capability(limit(threshold="60000")), "60000", "3321.67") == Artifact(
        OUTPUT, D("60000")
    )
    assert compute(capability(limit(threshold="60000")), "60000.01", "3321.67") == Artifact(
        OUTPUT, D("65775.64")
    )


def test_the_rate_comes_from_the_dataset() -> None:
    assert compute(capability(limit(rate="0.5")), "60000", "100") == Artifact(OUTPUT, D("200"))


def test_a_rate_of_one_gives_the_dividend() -> None:
    assert compute(capability(limit(rate="1")), "60000", "123.45") == Artifact(OUTPUT, D("123.45"))


# --- computing: rounding ------------------------------------------------------------------------


def test_the_division_is_rounded_once_half_up_to_the_cent() -> None:
    # 0.0025 / 0.5 = 0.005 exactly: half up gives 0.01 (half even would give 0.00).
    assert compute(capability(limit(rate="0.5")), "60000", "0.0025") == Artifact(OUTPUT, D("0.01"))


def test_a_quotient_just_under_the_half_cent_rounds_down() -> None:
    assert compute(capability(limit(rate="0.5")), "60000", "0.00249") == Artifact(OUTPUT, D("0.00"))


def test_a_passed_through_amount_is_rounded_by_the_datasets_rule() -> None:
    assert compute(capability(), "50000.005", "1") == Artifact(OUTPUT, D("50000.01"))
    assert compute(capability(), "50000.004", "1") == Artifact(OUTPUT, D("50000.00"))


def test_a_passed_through_amount_is_not_rounded_under_no_rounding() -> None:
    assert compute(capability(limit(rounding=NO_ROUNDING)), "50000.005", "1") == Artifact(
        OUTPUT, D("50000.005")
    )


def test_a_rounded_figure_carries_the_increments_scale() -> None:
    assert str(compute(capability(), "50000", "1").value) == "50000.00"
    assert str(compute(capability(), "60000", "3321.67").value) == "65775.64"


def test_the_rounding_rule_comes_from_the_dataset() -> None:
    whole = limit(rounding=RoundTo(D("1"), RoundingMode.HALF_UP))

    assert compute(capability(whole), "60000", "3321.67") == Artifact(OUTPUT, D("65776"))


def test_an_exact_division_under_no_rounding_is_kept_exactly() -> None:
    # 5.05 / 5.05% = 100.
    assert compute(capability(limit(rounding=NO_ROUNDING)), "60000", "5.05") == Artifact(
        OUTPUT, D("100")
    )


def test_an_inexact_division_under_no_rounding_raises_inexact() -> None:
    # 3,321.67 / 5.05% has no finite decimal expansion.
    with pytest.raises(decimal.Inexact):
        capability(limit(rounding=NO_ROUNDING)).compute(inputs("60000", "3321.67"))


def test_an_inexact_division_is_not_rounded_instead_under_no_rounding() -> None:
    with pytest.raises(decimal.Inexact):
        compute(capability(limit(rounding=NO_ROUNDING)), "60000", "3321.67")


def test_an_inexact_division_that_is_not_chosen_does_not_raise() -> None:
    # At or below the threshold the dividend is not divided at all.
    assert compute(capability(limit(rounding=NO_ROUNDING)), "50000", "3321.67") == Artifact(
        OUTPUT, D("50000")
    )


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("9"))

    result = capability().compute((other, *inputs("50000", "3321.67")))

    assert result.outputs == (Artifact(OUTPUT, D("50000")),)


def test_missing_amount_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="amount"):
        capability().compute((Artifact(DIVIDEND, D("3321.67")),))


def test_missing_dividend_is_a_missing_artifact_even_at_or_below_the_threshold() -> None:
    with pytest.raises(MissingArtifactError, match="dividend"):
        capability().compute((Artifact(AMOUNT, D("50000")),))


def test_has_one_output() -> None:
    assert len(capability().compute(inputs("60000", "3321.67")).outputs) == 1


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(inputs("60000", "3321.67")) == wired.compute(inputs("60000", "3321.67"))


# --- trace --------------------------------------------------------------------------------------


def line_of(
    amount: str,
    dividend: str,
    result: str,
    dataset: ParameterDataset[ThresholdRate] | None = None,
) -> Any:
    dataset = dataset or limit()
    return AmountOrDividedByRateLine(
        output=OUTPUT,
        amount_kind=AMOUNT,
        amount_value=D(amount),
        dividend_kind=DIVIDEND,
        dividend_value=D(dividend),
        limit=dataset.values,
        rounding=dataset.rounding,
        result=D(result),
    )


def test_traces_one_line_when_the_amount_passes_through() -> None:
    (line,) = capability().compute(inputs("50000", "3321.67")).trace

    assert line == line_of("50000", "3321.67", "50000.00")


def test_traces_one_line_when_the_dividend_is_divided() -> None:
    (line,) = capability().compute(inputs("60000", "3321.67")).trace

    assert line == line_of("60000", "3321.67", "65775.64")


def test_traces_the_datasets_threshold_rate_and_rounding_rule() -> None:
    dataset = limit(threshold="57375", rate="0.145", rounding=NO_ROUNDING)

    (line,) = capability(dataset).compute(inputs("57375", "10907.51")).trace

    assert isinstance(line, AmountOrDividedByRateLine)
    assert line.limit == ThresholdRate(Rate(D("0.145")), D("57375"))
    assert line.rounding == NO_ROUNDING
    assert line.amount_kind is AMOUNT
    assert line.dividend_kind is DIVIDEND
    assert line.output is OUTPUT


def test_trace_amount_is_the_result() -> None:
    trace = capability().compute(inputs("60000", "3321.67")).trace

    assert [line.amount for line in trace] == [D("65775.64")]


def test_trace_result_is_the_output() -> None:
    result = capability().compute(inputs("60000", "3321.67"))

    (line,) = result.trace
    (output,) = result.outputs
    assert isinstance(line, AmountOrDividedByRateLine)
    assert line.result == output.value


def test_trace_holds_no_text() -> None:
    trace = capability().compute(inputs("60000", "3321.67")).trace

    for line in trace:
        assert not any(isinstance(getattr(line, f.name), str) for f in fields(line))


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[ThresholdRate]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, THRESHOLD_RATE):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(dataset: ParameterDataset[ThresholdRate] | None = None) -> TaxComputationService:
    dataset = dataset or limit()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/amount_or_divided_by_rate",
        params={"limit": dataset.family},
        consumes={"amount": "ex/amount", "dividend": "ex/dividend"},
        produces={"output": "ex/out"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/amount", "ex/dividend"})),
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
    for kind in (AMOUNT, DIVIDEND, OUTPUT):
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
    assert isinstance(built, AmountOrDividedByRate)
    assert built.consumes == frozenset({AMOUNT, DIVIDEND})
    assert built.produces == frozenset({OUTPUT})


def test_a_computation_passes_the_amount_through_at_or_below_the_threshold() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *inputs("50000", "3321.67"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OUTPUT).value == D("50000")
    assert worksheet.trace == (line_of("50000", "3321.67", "50000.00"),)


def test_a_computation_divides_over_the_threshold() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *inputs("60000", "3321.67"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OUTPUT).value == D("65775.64")
    assert isinstance(worksheet.producer_of(OUTPUT), AmountOrDividedByRate)
    assert worksheet.trace == (line_of("60000", "3321.67", "65775.64"),)


def test_a_computation_with_an_inexact_division_and_no_rounding_names_the_capability() -> None:
    built = service(limit(rounding=NO_ROUNDING))

    with pytest.raises(CapabilityContractError, match=r"AmountOrDividedByRate .*inexact") as raised:
        built.compute(JurisdictionCode("CA-ON"), 2025, *inputs("60000", "3321.67"))

    assert isinstance(raised.value.__cause__, decimal.Inexact)
