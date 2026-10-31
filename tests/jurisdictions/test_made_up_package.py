"""A made-up jurisdiction needs only a package directory: NAMESPACE, a catalog, manifests and
parameters, read through the real sources. Names and values are made up."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tax_engine.adapters.outbound.jurisdiction_packages import JurisdictionPackages
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.adapters.outbound.yaml_parameters import YamlParameterSource
from tax_engine.domain.artifact import ArtifactCatalog, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection
from tax_engine.domain.parameters.brackets import BRACKETS, Bracket, BracketSchedule
from tax_engine.domain.registry import Namespace
from tax_engine.registrations import CORE_PACKAGES
from tests.jurisdictions.registration_fixtures import ex_on
from tests.jurisdictions.registration_fixtures.ex_on import catalog
from tests.jurisdictions.registration_fixtures.ex_on.catalog import CATALOG, LEVY, LEVY_BASE

D = Decimal
EX_ON = JurisdictionCode("EX-ON")
PACKAGES = JurisdictionPackages((ex_on,))


def test_the_package_directory_is_its_root() -> None:
    assert PACKAGES.roots() == {Namespace("ex-on"): Path(ex_on.__file__).parent}


def test_its_manifest_is_read_from_the_package() -> None:
    (manifest,) = YamlJurisdictionSource(PACKAGES.roots()).get_jurisdiction(EX_ON).manifests

    assert manifest.inputs.keys() == frozenset({"ex-on/levy_base"})
    (default,) = manifest.forms
    assert default.name == "ex-on/return"
    assert default.instances is None
    assert default.exports == ("ex-on/levy",)
    assert default.capabilities == (
        CapabilitySelection(
            name="core/progressive_tax",
            params={"schedule": "ex-on/brackets"},
            consumes={"base": "ex-on/levy_base"},
            produces={"output": "ex-on/levy"},
        ),
    )


def test_its_datasets_are_read_from_the_package() -> None:
    dataset = YamlParameterSource(PACKAGES.roots()).get("ex-on/brackets", 2025, BRACKETS)

    assert dataset.values == BracketSchedule(
        (Bracket(D("0"), D("0.10")), Bracket(D("100"), D("0.20")))
    )


def test_every_parameter_slot_has_a_dataset() -> None:
    (manifest,) = YamlJurisdictionSource(PACKAGES.roots()).get_jurisdiction(EX_ON).manifests
    parameters = YamlParameterSource(PACKAGES.roots())

    assert CORE_PACKAGES  # importing them filled the capability and parser registries
    for selection in manifest.forms[0].capabilities:
        slots = CapabilityRegistry.shared().get(selection.name).PARAMETERS
        assert set(selection.params) == set(slots)
        for slot, family in selection.params.items():
            kind = slots[slot]
            assert parameters.get(family, manifest.valid_from_tax_year, kind).kind is kind


def test_every_artifact_slot_names_a_kind_of_its_catalog() -> None:
    (manifest,) = YamlJurisdictionSource(PACKAGES.roots()).get_jurisdiction(EX_ON).manifests
    declared = {"ex-on/levy_base", "ex-on/levy"}  # see the catalog test below

    for selection in manifest.forms[0].capabilities:
        assert set(selection.consumes.values()) | set(selection.produces.values()) <= declared


def test_it_exposes_its_catalog() -> None:
    assert isinstance(catalog.CATALOG, ArtifactCatalog)
    assert catalog.CATALOG is CATALOG
    assert CATALOG.kinds == (LEVY_BASE, LEVY)


def test_its_catalog_registers_explicitly_in_its_namespace() -> None:
    registry = ArtifactRegistry()

    PACKAGES.register(registry)

    assert registry.identifiers() == {"ex-on/levy_base", "ex-on/levy"}
    assert registry.get("ex-on/levy_base") is LEVY_BASE
    assert registry.get("ex-on/levy") is LEVY
