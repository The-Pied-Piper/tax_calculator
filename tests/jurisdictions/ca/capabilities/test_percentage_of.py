"""Unit tests for the PercentageOf capability (`ca/percentage_of`), with made-up kinds.

A percentage of two money figures: the consumed `dividend` over the consumed `divisor`, times 100,
rounded once by a `rounding_only` dataset (a form line such as "Percentage (%) ... Row 1 divided
by row 2" is the dataset with increment 0.01 and mode half up). Its slots: one parameter slot
`rounding` (a `rounding_only` dataset), two consumed slots `dividend` and `divisor` (`Decimal`
kinds), one produced slot `output`, a `Decimal` kind holding the percent: 60 means 60%.

The output is `rounding.apply(100 x dividend / divisor)`, the quotient an exact fraction. A zero
divisor gives 0, never an error. The capability is built like `ca/ratio_truncated`: it is looked
up in the registry, and built from its slot names as keywords.

Worked example: 60,000 / 100,000 is 60%; 1 / 3 is 33.333..., which rounds half up to 33.33.
"""

from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any

import pytest

import tax_engine.jurisdictions.ca.capabilities  # noqa: F401  (registers the federal capabilities)
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
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)
from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY, RoundingOnly
from tax_engine.jurisdictions.ca.trace import PercentageOfLine
from tests.manifest_support import required_inputs

D = Decimal
CENT_HALF_UP = RoundTo(D("0.01"), RoundingMode.HALF_UP)

DIVIDEND = ArtifactKind("ex/part_gross", Decimal)
DIVISOR = ArtifactKind("ex/all_gross", Decimal)
OUTPUT = ArtifactKind("ex/gross_share_percent", Decimal)


def percentage_of() -> Any:
    return CapabilityRegistry.shared().get("ca/percentage_of")


def rounding(rule: RoundingRule = CENT_HALF_UP) -> ParameterDataset[RoundingOnly]:
    return ParameterDataset(
        "ex/share_percent_rounding",
        2025,
        ROUNDING_ONLY,
        RoundingOnly(),
        rule,
        ("https://example.org/p",),
    )


def capability(data: ParameterDataset[RoundingOnly] | None = None) -> Any:
    return percentage_of()(
        rounding=data or rounding(), dividend=DIVIDEND, divisor=DIVISOR, output=OUTPUT
    )


def inputs(dividend: str, divisor: str) -> tuple[Artifact[Any], ...]:
    return (Artifact(DIVIDEND, D(dividend)), Artifact(DIVISOR, D(divisor)))


def compute(wired: Any, dividend: str, divisor: str) -> Artifact[Any]:
    output: Artifact[Any] = wired.compute(inputs(dividend, divisor)).outputs[0]
    return output


def test_is_registered_as_ca_percentage_of() -> None:
    assert CapabilityRegistry.shared().get("ca/percentage_of") is percentage_of()


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({DIVIDEND, DIVISOR})
    assert capability().produces == frozenset({OUTPUT})


def test_declares_its_slots() -> None:
    cls = percentage_of()

    assert cls.PARAMETERS == {"rounding": ROUNDING_ONLY}
    assert cls.CONSUMES == {"dividend": Decimal, "divisor": Decimal}
    assert cls.PRODUCES == {"output": Decimal}
    assert not cls.is_list_slot("dividend")
    assert not cls.is_list_slot("divisor")


def test_its_slots_cannot_be_changed() -> None:
    cls = percentage_of()

    for slots in (cls.PARAMETERS, cls.CONSUMES, cls.PRODUCES):
        with pytest.raises(TypeError):
            slots["extra"] = Decimal


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = percentage_of()(rounding=rounding(), dividend=DIVIDEND, divisor=DIVISOR, output=OUTPUT)

    assert compute(wired, "60000", "100000") == Artifact(OUTPUT, D("60.00"))


def test_rejects_one_kind_in_two_slots() -> None:
    with pytest.raises(InvalidCapabilityError) as raised:
        percentage_of()(rounding(), DIVIDEND, DIVIDEND, OUTPUT)

    assert "'dividend'" in str(raised.value)
    assert "'divisor'" in str(raised.value)


def test_rejects_a_list_of_kinds_for_its_dividend() -> None:
    with pytest.raises(InvalidCapabilityError, match="'dividend'"):
        percentage_of()(rounding(), (DIVIDEND,), DIVISOR, OUTPUT)


# --- computing: the percent ---------------------------------------------------------------------


def test_sixty_thousand_of_one_hundred_thousand_is_60_percent() -> None:
    # 100 x 60,000 / 100,000 = 60: the worked example's row 3 (60 means 60%).
    output = compute(capability(), "60000", "100000")

    assert output == Artifact(OUTPUT, D("60"))
    assert type(output.value) is Decimal


def test_fifteen_thousand_of_thirty_thousand_is_50_percent() -> None:
    # 100 x 15,000 / 30,000 = 50: the worked example's row 6.
    assert compute(capability(), "15000", "30000") == Artifact(OUTPUT, D("50"))


def test_one_third_rounds_half_up_to_the_cent_of_a_percent() -> None:
    # 100 x 1 / 3 = 33.3333..., to two decimals of a percent: 33.33.
    assert compute(capability(), "1", "3") == Artifact(OUTPUT, D("33.33"))


def test_two_thirds_rounds_half_up_not_down() -> None:
    # 100 x 2 / 3 = 66.6666..., which rounds up to 66.67.
    assert compute(capability(), "2", "3") == Artifact(OUTPUT, D("66.67"))


def test_a_half_cent_of_a_percent_rounds_up() -> None:
    # 100 x 1 / 800 = 0.125 exactly, which rounds half up to 0.13 (not half to even, 0.12).
    assert compute(capability(), "1", "800") == Artifact(OUTPUT, D("0.13"))


def test_a_finite_percent_is_kept_exactly() -> None:
    # 100 x 1 / 8 = 12.5.
    assert compute(capability(), "1", "8") == Artifact(OUTPUT, D("12.5"))


def test_the_percent_is_one_exact_fraction_not_a_float() -> None:
    # 100 x 999,999 / 1,000,000 = 99.9999, which rounds half up to 100.00: no float error shows.
    assert compute(capability(), "999999", "1000000") == Artifact(OUTPUT, D("100.00"))


def test_a_zero_dividend_gives_zero() -> None:
    assert compute(capability(), "0", "100000") == Artifact(OUTPUT, D("0"))


def test_a_zero_divisor_gives_zero_not_an_error() -> None:
    output = compute(capability(), "60000", "0")

    assert output == Artifact(OUTPUT, D("0"))
    assert type(output.value) is Decimal


def test_a_zero_dividend_over_a_zero_divisor_gives_zero() -> None:
    assert compute(capability(), "0", "0") == Artifact(OUTPUT, D("0"))


def test_an_exact_percent_under_no_rounding_is_kept_exactly() -> None:
    wired = capability(rounding(NO_ROUNDING))

    assert compute(wired, "1", "4") == Artifact(OUTPUT, D("25"))


def test_an_inexact_percent_under_no_rounding_is_refused() -> None:
    with pytest.raises(decimal.Inexact):
        capability(rounding(NO_ROUNDING)).compute(inputs("1", "3"))


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("9"))

    result = capability().compute((other, *inputs("1", "4")))

    assert result.outputs == (Artifact(OUTPUT, D("25.00")),)


def test_a_missing_dividend_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="part_gross"):
        capability().compute((Artifact(DIVISOR, D("1")),))


def test_a_missing_divisor_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="all_gross"):
        capability().compute((Artifact(DIVIDEND, D("1")),))


def test_has_one_output_and_is_repeatable() -> None:
    wired = capability()

    assert len(wired.compute(inputs("1", "3")).outputs) == 1
    assert wired.compute(inputs("1", "3")) == wired.compute(inputs("1", "3"))


# --- trace: the line is emitted (its fields and English text are tested in the trace modules) ----


def test_traces_one_percentage_line_with_the_percent_it_produced() -> None:
    result = capability().compute(inputs("60000", "100000"))

    assert result.trace == (
        PercentageOfLine(OUTPUT, DIVIDEND, D("60000"), DIVISOR, D("100000"), CENT_HALF_UP, D("60")),
    )
    assert result.trace[0].amount == result.outputs[0].value


def test_a_zero_divisor_traces_a_zero_percent_line() -> None:
    assert capability().compute(inputs("5", "0")).trace == (
        PercentageOfLine(OUTPUT, DIVIDEND, D("5"), DIVISOR, D("0"), CENT_HALF_UP, D("0")),
    )


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
        return self._dataset  # type: ignore[return-value]


def service(dataset: ParameterDataset[RoundingOnly] | None = None) -> TaxComputationService:
    dataset = dataset or rounding()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/percentage_of",
        params={"rounding": dataset.family},
        consumes={"dividend": "ex/part_gross", "divisor": "ex/all_gross"},
        produces={"output": "ex/gross_share_percent"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/part_gross", "ex/all_gross"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/gross_share_percent",),
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


def test_a_computation_builds_the_capability_and_gives_the_percent() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, *inputs("60000", "100000"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OUTPUT).value == D("60")
    assert isinstance(worksheet.producer_of(OUTPUT), percentage_of())


def test_a_computation_with_an_inexact_percent_and_no_rounding_names_the_capability() -> None:
    built = service(rounding(NO_ROUNDING))

    with pytest.raises(CapabilityContractError, match="PercentageOf|ca/percentage_of"):
        built.compute(JurisdictionCode("CA-ON"), 2025, *inputs("1", "3"))
