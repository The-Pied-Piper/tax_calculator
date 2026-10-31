"""The shared fact "non active partnership losses" in the CA-ON manifest: a form of its own, with no
instances, and what the form `ca/t2048` reads of it.

The form `ca/non_active_partnership_losses` is run once on the one input
`ca/non_active_partnership_losses`, which it exports as it is; it has no step. It is in the part
`01j_non_active_partnership_losses.yaml` under the `form:` key. The entries are listed in
`manifest_families/non_active_partnership_losses.py`. The form `ca/t2048` reads the derived kind
`ca/non_active_partnership_losses.non_active_partnership_losses` as the total
`ca/qbt_partnership_losses`, Chart A line 3, so the amount is entered once for every disposition and
cannot disagree with itself; it is not a field of the record list `ca/t2048_dispositions` any more.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tax_engine.jurisdictions.ca.catalog import T2048_DISPOSITIONS
from tests.jurisdictions.ca_on.manifest_families import non_active_partnership_losses

CA_ON = JurisdictionCode("CA-ON")
FORM = "ca/non_active_partnership_losses"
DERIVED = "ca/non_active_partnership_losses.non_active_partnership_losses"
TOTAL = "ca/qbt_partnership_losses"
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "01j_non_active_partnership_losses.yaml"
)


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (found for found in manifest().forms if found.name == FORM)
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form(FORM)


def test_the_part_declares_the_form_with_its_export_and_no_instances() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": FORM,
        "required": True,
        "exports": list(non_active_partnership_losses.FORM_EXPORTS),
    }


def test_the_part_is_a_form_of_its_own_and_adds_no_step_to_the_return() -> None:
    declared = yaml.safe_load(PART.read_text())

    assert set(declared) <= {"form", "capabilities"}
    assert not declared.get("capabilities")


def test_the_manifest_has_the_form_with_no_instances_and_the_input_as_its_export() -> None:
    found = form()

    assert found.instances is None
    assert found.exports == non_active_partnership_losses.FORM_EXPORTS


def test_the_form_holds_no_selection_of_its_own() -> None:
    found = form()

    assert len(found.capabilities) == 0
    assert set(found.capabilities) == non_active_partnership_losses.FORM_STEPS


def test_the_one_input_is_a_manifest_input() -> None:
    assert non_active_partnership_losses.INPUTS <= manifest().inputs.keys()
    assert len(non_active_partnership_losses.INPUTS) == 1


def test_the_t2048_record_list_no_longer_holds_the_amount() -> None:
    assert "ca/qbt_partnership_losses" not in {
        field.identifier for field in T2048_DISPOSITIONS.fields
    }


def test_the_form_runs_once_and_derives_the_kind_of_its_export() -> None:
    found = composed()

    assert found.instances is None
    assert {kind.identifier for kind in found.imports} == set()
    assert [kind.identifier for kind in found.derived] == [DERIVED]


def test_the_composed_form_has_no_step() -> None:
    assert len(composed().composition.order) == 0


def test_the_t2048_form_imports_the_derived_kind_and_reads_it_as_a_total() -> None:
    form_t2048 = build_tax_computation().compose(CA_ON, 2025).form("ca/t2048")

    assert DERIVED in {kind.identifier for kind in form_t2048.imports}
    (total,) = (
        capability
        for capability in form_t2048.composition.order
        if {kind.identifier for kind in capability.produces} == {TOTAL}
    )
    assert {kind.identifier for kind in total.consumes} == {DERIVED}
