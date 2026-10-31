"""The shared fact "has investment expenses in 2025" in the CA-ON manifest: a form of its own, with
no instances, and what the form `ca/t2048` reads of it.

The form `ca/has_investment_expenses` is run once on the one input `ca/has_investment_expenses`;
its one step checks the answer to be 0 or 1 and it exports the checked count. It is in the part
`01n_has_investment_expenses.yaml` under the `form:` key. The entries are listed in
`manifest_families/has_investment_expenses.py`. The form `ca/t2048` (Part 3 line 24), run once for
each disposition, imports the export as the derived kind
`ca/has_investment_expenses.has_investment_expenses_checked` and takes its first value, so the
answer is given once for every disposition and cannot disagree with itself; it is not a field of
the record list `ca/t2048_dispositions`.
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
from tests.jurisdictions.ca_on.manifest_families import has_investment_expenses

CA_ON = JurisdictionCode("CA-ON")
FORM = "ca/has_investment_expenses"
DERIVED = "ca/has_investment_expenses.has_investment_expenses_checked"
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "01n_has_investment_expenses.yaml"
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
        "exports": list(has_investment_expenses.FORM_EXPORTS),
    }


def test_the_part_is_a_form_of_its_own_and_adds_no_step_to_the_return() -> None:
    assert set(yaml.safe_load(PART.read_text())) == {"form", "capabilities"}


def test_the_manifest_has_the_form_with_no_instances_and_the_checked_count_export() -> None:
    found = form()

    assert found.instances is None
    assert found.exports == has_investment_expenses.FORM_EXPORTS


def test_the_form_holds_the_one_selection_that_checks_the_answer() -> None:
    found = form()

    assert len(found.capabilities) == 1
    assert set(found.capabilities) == has_investment_expenses.FORM_STEPS


def test_the_return_selects_none_of_the_forms_steps() -> None:
    (default, *_) = manifest().forms

    assert set(default.capabilities).isdisjoint(has_investment_expenses.FORM_STEPS)


def test_the_one_input_is_a_manifest_input() -> None:
    assert has_investment_expenses.INPUTS <= manifest().inputs.keys()
    assert len(has_investment_expenses.INPUTS) == 1


def test_the_t2048_record_list_no_longer_holds_the_answer() -> None:
    assert "ca/qbt_has_investment_expenses" not in {
        field.identifier for field in T2048_DISPOSITIONS.fields
    }


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

    assert has_investment_expenses.FORM_WIRING <= wiring


def test_the_t2048_form_imports_the_derived_kind_and_takes_its_first_value() -> None:
    form_t2048 = build_tax_computation().compose(CA_ON, 2025).form("ca/t2048")

    assert DERIVED in {kind.identifier for kind in form_t2048.imports}
    (total,) = (
        capability
        for capability in form_t2048.composition.order
        if {kind.identifier for kind in capability.produces} == {"ca/qbt_has_investment_expenses"}
    )
    assert {kind.identifier for kind in total.consumes} == {DERIVED}
