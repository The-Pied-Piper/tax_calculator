"""Unit tests for Jurisdiction.manifest_for: which stored manifest applies to a tax year.

The manifest with the greatest `valid_from_tax_year` not after the tax year applies; a tax year
before every manifest has none, and two manifests sharing that greatest year are ambiguous.
Codes, identifiers and versions are made up.
"""

from __future__ import annotations

from typing import assert_type

import pytest

from tax_engine.domain.errors import AmbiguousManifestError, DomainError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tests.manifest_support import required_inputs

EX_ON = JurisdictionCode("EX-ON")


def manifest(version: int, valid_from_tax_year: int) -> Manifest:
    return Manifest(
        jurisdiction=EX_ON,
        version=version,
        valid_from_tax_year=valid_from_tax_year,
        inputs=required_inputs(frozenset({"ex/levy_base"})),
        forms=(
            Form(
                required=True,
                name="ex-on/return",
                instances=None,
                exports=("ex/levy",),
                capabilities=(
                    CapabilitySelection(
                        name="ex/levy",
                        params={},
                        consumes={"base": "ex/levy_base"},
                        produces={"output": "ex/levy"},
                    ),
                ),
            ),
        ),
    )


V1 = manifest(version=1, valid_from_tax_year=2025)
V2 = manifest(version=2, valid_from_tax_year=2027)
V3 = manifest(version=3, valid_from_tax_year=2030)


def jurisdiction(*manifests: Manifest) -> Jurisdiction:
    return Jurisdiction(code=EX_ON, manifests=manifests)


def test_returns_a_manifest() -> None:
    found = jurisdiction(V1).manifest_for(2025)

    assert_type(found, Manifest)
    assert found is V1


@pytest.mark.parametrize(
    ("tax_year", "expected"),
    [
        pytest.param(2025, V1, id="first-year-of-v1"),
        pytest.param(2026, V1, id="later-year-of-v1"),
        pytest.param(2027, V2, id="first-year-of-v2"),
        pytest.param(2029, V2, id="last-year-of-v2"),
        pytest.param(2030, V3, id="first-year-of-v3"),
        pytest.param(2099, V3, id="far-future"),
    ],
)
def test_picks_the_latest_manifest_valid_from_on_or_before_the_tax_year(
    tax_year: int, expected: Manifest
) -> None:
    assert jurisdiction(V1, V2, V3).manifest_for(tax_year) is expected


def test_the_stored_order_of_manifests_does_not_matter() -> None:
    assert jurisdiction(V3, V1, V2).manifest_for(2028) is V2


def test_a_tax_year_before_every_manifest_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="EX-ON.*2024|2024.*EX-ON"):
        jurisdiction(V1, V2).manifest_for(2024)


def test_a_jurisdiction_without_manifests_has_none_for_any_year() -> None:
    with pytest.raises(NotFoundError, match="EX-ON.*2025|2025.*EX-ON"):
        jurisdiction().manifest_for(2025)


def test_two_manifests_valid_from_the_same_best_year_are_ambiguous() -> None:
    rival = manifest(version=4, valid_from_tax_year=2027)

    with pytest.raises(AmbiguousManifestError) as excinfo:
        jurisdiction(V1, V2, rival).manifest_for(2028)
    with pytest.raises(AmbiguousManifestError, match="versions 2, 4"):
        jurisdiction(rival, V2, V1).manifest_for(2028)  # order of storage must not matter

    message = str(excinfo.value)
    for part in ("EX-ON", "2028", "2027", "versions 2, 4"):
        assert part in message, message
    assert issubclass(AmbiguousManifestError, DomainError)


def test_a_shared_year_that_is_not_the_best_is_not_ambiguous() -> None:
    rival = manifest(version=4, valid_from_tax_year=2025)

    assert jurisdiction(V1, rival, V2).manifest_for(2028) is V2
