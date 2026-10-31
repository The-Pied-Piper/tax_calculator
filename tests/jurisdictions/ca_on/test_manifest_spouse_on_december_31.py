"""The shared fact "spouse on December 31" in the CA-ON manifest: a form of its own, with no
instances, and what the return reads of it.

The form `ca/spouse_on_december_31` is run once on the one input
`ca/spouse_or_common_law_partner_on_december_31`; its one step checks the answer to be 0 or 1 and
it exports the checked count. It is in the part `01e_spouse_on_december_31.yaml` under the `form:`
key. The entries are listed in `manifest_families/spouse_on_december_31.py`. The return (ON428's
rule before lines 75 and 76 and Schedule ON428-A's Part A or Part B choice) imports the export as
the derived kind `ca/spouse_on_december_31.spouse_or_common_law_partner_on_december_31_checked`.
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
from tests.jurisdictions.ca_on.manifest_families import spouse_on_december_31

CA_ON = JurisdictionCode("CA-ON")
FORM = "ca/spouse_on_december_31"
DERIVED = "ca/spouse_on_december_31.spouse_or_common_law_partner_on_december_31_checked"
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "01e_spouse_on_december_31.yaml"
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
        "exports": list(spouse_on_december_31.FORM_EXPORTS),
    }


def test_the_part_is_a_form_of_its_own_and_adds_no_step_to_the_return() -> None:
    assert set(yaml.safe_load(PART.read_text())) == {"form", "capabilities"}


def test_the_manifest_has_the_form_with_no_instances_and_the_checked_count_export() -> None:
    found = form()

    assert found.instances is None
    assert found.exports == spouse_on_december_31.FORM_EXPORTS


def test_the_form_holds_the_one_selection_that_checks_the_answer() -> None:
    found = form()

    assert len(found.capabilities) == 1
    assert set(found.capabilities) == spouse_on_december_31.FORM_STEPS


def test_the_return_selects_none_of_the_forms_steps() -> None:
    (default, *_) = manifest().forms

    assert set(default.capabilities).isdisjoint(spouse_on_december_31.FORM_STEPS)


def test_the_one_input_is_a_manifest_input() -> None:
    assert spouse_on_december_31.INPUTS <= manifest().inputs.keys()
    assert len(spouse_on_december_31.INPUTS) == 1


def test_the_manifest_has_no_lift_spouse_input_any_more() -> None:
    assert "ca-on/lift_spouse_at_year_end" not in manifest().inputs.keys()


def test_the_form_runs_once_and_derives_the_kind_of_its_export() -> None:
    found = composed()

    assert found.instances is None
    assert {kind.identifier for kind in found.imports} == set()
    assert [kind.identifier for kind in found.derived] == [DERIVED]


def test_the_composed_form_has_the_wiring_of_the_family() -> None:
    wiring = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert spouse_on_december_31.FORM_WIRING <= wiring


def test_the_return_imports_the_derived_kind_and_reads_it_as_a_total() -> None:
    returned = build_tax_computation().compose(CA_ON, 2025).form("ca-on/return")

    assert DERIVED in {kind.identifier for kind in returned.imports}
    (total,) = (
        capability
        for capability in returned.composition.order
        if {kind.identifier for kind in capability.produces}
        == {"ca/spouse_or_common_law_partner_on_december_31_total"}
    )
    assert {kind.identifier for kind in total.consumes} == {DERIVED}
