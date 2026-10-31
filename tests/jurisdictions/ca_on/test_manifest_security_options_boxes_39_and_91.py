"""The shared fact "T4 boxes 39 and 91" in the CA-ON manifest: a form of its own, with no instances,
and what the return reads of it.

The form `ca/security_options_boxes_39_and_91` is run once on the one input
`ca/t4_security_options_boxes_39_and_91`, which it exports as it is; it has no step. It is in the
part `01f_security_options_boxes_39_and_91.yaml` under the `form:` key. The entries are listed in
`manifest_families/security_options_boxes_39_and_91.py`. The return reads the derived kind
`ca/security_options_boxes_39_and_91.t4_security_options_boxes_39_and_91` as the total
`ca/t4_security_options_boxes_39_and_91_total`, which the line 24900 sum and Form T691 line 28 both
read, so the amount is entered once and cannot disagree with itself. The line 24900 deduction is
not an input of the return any more: the return computes it.
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
from tax_engine.jurisdictions.ca.catalog import (
    AMT_SECURITY_OPTIONS_D_TOTAL,
    SECURITY_OPTIONS_DEDUCTIONS,
)
from tests.jurisdictions.ca_on.manifest_families import security_options_boxes_39_and_91

CA_ON = JurisdictionCode("CA-ON")
FORM = "ca/security_options_boxes_39_and_91"
DERIVED = "ca/security_options_boxes_39_and_91.t4_security_options_boxes_39_and_91"
TOTAL = "ca/t4_security_options_boxes_39_and_91_total"
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "01f_security_options_boxes_39_and_91.yaml"
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
        "exports": list(security_options_boxes_39_and_91.FORM_EXPORTS),
    }


def test_the_part_is_a_form_of_its_own_and_adds_no_step_to_the_return() -> None:
    declared = yaml.safe_load(PART.read_text())

    assert set(declared) <= {"form", "capabilities"}
    assert not declared.get("capabilities")


def test_the_manifest_has_the_form_with_no_instances_and_the_input_as_its_export() -> None:
    found = form()

    assert found.instances is None
    assert found.exports == security_options_boxes_39_and_91.FORM_EXPORTS


def test_the_form_holds_no_selection_of_its_own() -> None:
    found = form()

    assert len(found.capabilities) == 0
    assert set(found.capabilities) == security_options_boxes_39_and_91.FORM_STEPS


def test_the_one_input_is_a_manifest_input() -> None:
    assert security_options_boxes_39_and_91.INPUTS <= manifest().inputs.keys()
    assert len(security_options_boxes_39_and_91.INPUTS) == 1


def test_the_manifest_has_no_amt_named_box_input_any_more() -> None:
    assert "ca/amt_t4_security_options_boxes_39_and_91" not in manifest().inputs.keys()


def test_the_manifest_has_no_security_options_deductions_input_any_more() -> None:
    # Guide 5000-G line 24900 "Claim on line 24900 of your return the total of the amounts shown in
    # boxes 39, 41, 91, and 92 of your T4 slips": the line is the total of the T4 boxes, computed.
    assert "ca/security_options_deductions" not in manifest().inputs.keys()


def test_the_form_runs_once_and_derives_the_kind_of_its_export() -> None:
    found = composed()

    assert found.instances is None
    assert {kind.identifier for kind in found.imports} == set()
    assert [kind.identifier for kind in found.derived] == [DERIVED]


def test_the_composed_form_has_no_step() -> None:
    assert len(composed().composition.order) == 0


def test_the_return_imports_the_derived_kind_and_reads_it_as_a_total() -> None:
    returned = build_tax_computation().compose(CA_ON, 2025).form("ca-on/return")

    assert DERIVED in {kind.identifier for kind in returned.imports}
    (total,) = (
        capability
        for capability in returned.composition.order
        if {kind.identifier for kind in capability.produces} == {TOTAL}
    )
    assert {kind.identifier for kind in total.consumes} == {DERIVED}


def test_the_line_24900_sum_and_t691_line_30_both_read_the_total() -> None:
    # T691 Part 1 line 28 is the total of boxes 39 and 91, and line 30 "Line 28 plus line 29" is
    # the sum that reads it; the line 24900 sum reads the same total, in T691 line order.
    returned = build_tax_computation().compose(CA_ON, 2025).form("ca-on/return")

    def consumed_for(identifier: str) -> set[str]:
        return {
            kind.identifier
            for capability in returned.composition.order
            if {produced.identifier for produced in capability.produces} == {identifier}
            for kind in capability.consumes
        }

    assert TOTAL in consumed_for(SECURITY_OPTIONS_DEDUCTIONS.identifier)
    assert TOTAL in consumed_for(AMT_SECURITY_OPTIONS_D_TOTAL.identifier)
