"""Unit tests for the YearAmount capability (`ca/year_amount`), with made-up kinds.

The figure a form prints for the year something was entered into: the `amount` of the row of a
`year_amounts` dataset that applies to the consumed `year`. Its slots: one parameter slot `amounts`
(a `year_amounts` dataset), one consumed slot `year` (an `int` kind), one produced slot `output`
(a `Decimal` kind). A year before the oldest dated row uses the open-ended row; a year after the
dataset's tax year is an `InputAboveBoundError`.

Worked example: with rows 2025 (44,706), 2024 (43,529), 2023 (42,353) and any earlier year
(35,294), a lease entered into in 2024 gives 43,529 and one entered into in 2019 gives 35,294.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import tax_engine.jurisdictions.ca.capabilities  # noqa: F401  (registers the federal capabilities)
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    InputAboveBoundError,
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rounding import NO_ROUNDING
from tax_engine.domain.parameters.year_amounts import YEAR_AMOUNTS, YearAmounts, YearAmountsRow
from tax_engine.jurisdictions.ca.trace import YearAmountLine
from tests.manifest_support import required_inputs

D = Decimal

YEAR = ArtifactKind("ex/lease_year", int)
OUTPUT = ArtifactKind("ex/list_price_limit", Decimal)


def row(from_year: int | None, amount: str) -> YearAmountsRow:
    return YearAmountsRow(from_year, {"amount": D(amount)})


def dataset() -> ParameterDataset[YearAmounts]:
    rows = (row(2025, "44706"), row(2024, "43529"), row(2023, "42353"), row(None, "35294"))
    return ParameterDataset(
        "ex/list_price_limit",
        2025,
        YEAR_AMOUNTS,
        YearAmounts(rows),
        NO_ROUNDING,
        ("https://example.org/p",),
    )


def year_amount() -> Any:
    return CapabilityRegistry.shared().get("ca/year_amount")


def wired() -> Any:
    return year_amount()(amounts=dataset(), year=YEAR, output=OUTPUT)


def compute(year: int) -> Any:
    return wired().compute((Artifact(YEAR, year),))


def test_is_registered_as_ca_year_amount() -> None:
    assert year_amount().__module__ == "tax_engine.jurisdictions.ca.capabilities.year_amount"


def test_declares_its_slots() -> None:
    cls = year_amount()

    assert cls.PARAMETERS == {"amounts": YEAR_AMOUNTS}
    assert cls.CONSUMES == {"year": int}
    assert cls.PRODUCES == {"output": Decimal}
    assert wired().consumes == frozenset({YEAR})
    assert wired().produces == frozenset({OUTPUT})


def test_rejects_a_list_of_kinds_for_its_year() -> None:
    with pytest.raises(InvalidCapabilityError, match="'year'"):
        year_amount()(dataset(), (YEAR,), OUTPUT)


@pytest.mark.parametrize(
    ("year", "amount"),
    [
        (2025, "44706"),
        (2024, "43529"),
        (2023, "42353"),
        (2022, "35294"),
        (2021, "35294"),
        (0, "35294"),
    ],
)
def test_gives_the_amount_printed_for_the_year(year: int, amount: str) -> None:
    assert compute(year).outputs == (Artifact(OUTPUT, D(amount)),)


def test_a_year_after_the_tax_year_is_refused() -> None:
    with pytest.raises(InputAboveBoundError, match="2026"):
        compute(2026)


def test_records_one_year_amount_line() -> None:
    assert compute(2024).trace == (YearAmountLine(OUTPUT, YEAR, 2024, D("43529")),)


def test_is_built_from_its_slot_names_as_keywords() -> None:
    assert compute(2025).outputs == (Artifact(OUTPUT, D("44706")),)


def test_rejects_one_kind_in_two_slots() -> None:
    with pytest.raises(InvalidCapabilityError):
        year_amount()(dataset(), OUTPUT, OUTPUT)


def test_a_missing_year_is_a_missing_artifact_error() -> None:
    with pytest.raises(MissingArtifactError):
        wired().compute(())


def test_its_slots_cannot_be_changed() -> None:
    cls = year_amount()

    for slots in (cls.PARAMETERS, cls.CONSUMES, cls.PRODUCES):
        with pytest.raises(TypeError):
            slots["extra"] = Decimal


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        data = dataset()
        if (family, tax_year, kind) != (data.family, 2025, YEAR_AMOUNTS):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return data  # type: ignore[return-value]


def service() -> TaxComputationService:
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/year_amount",
        params={"amounts": dataset().family},
        consumes={"year": "ex/lease_year"},
        produces={"output": "ex/list_price_limit"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ex/lease_year"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/list_price_limit",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (YEAR, OUTPUT):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_and_gives_the_amount() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, Artifact(YEAR, 2023))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OUTPUT).value == D("42353")
    assert isinstance(worksheet.producer_of(OUTPUT), year_amount())


def test_a_computation_with_a_year_after_2025_names_the_year() -> None:
    with pytest.raises(InputAboveBoundError, match="2026"):
        service().compute(JurisdictionCode("CA-ON"), 2025, Artifact(YEAR, 2026))
