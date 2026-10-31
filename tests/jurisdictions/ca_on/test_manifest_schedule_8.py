"""Schedule 8 in the CA-ON manifest: a form of none or one copy, and what the return reads.

Schedule 8, the Canada Pension Plan contributions and overpayment, is the form `ca/schedule_8`, run
once for the one copy of the form the return carries (none, with an empty
`ca/schedule_8_instances`). Its selections are in the parts `05c_schedule_8_part_3.yaml` to
`05h_schedule_8_contributions.yaml` under the `form:` key; the record has no fields, because every
figure the form reads is a starting amount of the return; and the return reads the seven lines it
uses through the totals of `05i_schedule_8_totals.yaml`. The entries of the form are listed in
`manifest_families/schedule_8.py` and the three `deductions_schedule_8_part_5*.py` modules.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.artifact import ArtifactRegistry
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca.catalog import SCHEDULE_8_INSTANCES
from tests.jurisdictions.ca_on.manifest_families import (
    deductions_schedule_8_part_5,
    deductions_schedule_8_part_5_contributions,
    deductions_schedule_8_part_5_other_earnings,
    schedule_8,
)
from tests.jurisdictions.ca_on.manifest_support import instance_fields, required_entries

CA_ON = JurisdictionCode("CA-ON")
PARTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
FORM_PARTS = (
    "05c_schedule_8_part_3.yaml",
    "05d_schedule_8_part_3b.yaml",
    "05e_schedule_8_part_5.yaml",
    "05f_schedule_8_part_5_contributions.yaml",
    "05g_schedule_8_part_5_other_earnings.yaml",
    "05h_schedule_8_contributions.yaml",
)
FAMILIES = (
    schedule_8,
    deductions_schedule_8_part_5,
    deductions_schedule_8_part_5_contributions,
    deductions_schedule_8_part_5_other_earnings,
)
FORM_STEPS = set[CapabilitySelection]().union(*(family.FORM_STEPS for family in FAMILIES))
FORM_WIRING = set[object]().union(*(family.FORM_WIRING for family in FAMILIES))
# The steps the form copies from the return, which the return keeps: Part 2 lines B to E, Part 4
# line 1 and the net self-employment income it adds with the three totals it reads.
COPIED_PRODUCTS = {
    "ca/cpp_maximum_pensionable_earnings",
    "ca/cpp_second_additional_earnings_maximum",
    "ca/cpp_additional_maximum_pensionable_earnings",
    "ca/cpp_basic_exemption",
    "ca/pensionable_net_self_employment_earnings",
    "ca/business_income",
    "ca/professional_income",
    "ca/commission_income",
    "ca/farming_income",
    "ca/fishing_income",
    "ca/net_self_employment_income",
}


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (found for found in manifest().forms if found.name == "ca/schedule_8")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/schedule_8")


# --- the parts and the form ----------------------------------------------------------------------


def test_the_first_part_declares_the_form_with_its_instances_limits_and_exports() -> None:
    declared = yaml.safe_load((PARTS / FORM_PARTS[0]).read_text())["form"]

    assert declared == {
        "name": "ca/schedule_8",
        "required": True,
        "fields": required_entries(instance_fields("ca/schedule_8")),
        "instances": "ca/schedule_8_instances",
        "max_instances": 1,
        "min_instances": 0,
        "exclusive_group": "ca/cpp_calculation",
        "exports": list(schedule_8.FORM_EXPORTS),
    }


def test_every_other_part_of_the_form_names_it_and_declares_nothing_else() -> None:
    for name in FORM_PARTS[1:]:
        assert yaml.safe_load((PARTS / name).read_text())["form"] == {"name": "ca/schedule_8"}, name


def test_the_manifest_has_the_form_schedule_8_beside_the_other_forms() -> None:
    found = form()

    assert found.name == "ca/schedule_8"
    assert found.instances == "ca/schedule_8_instances"
    assert found.exports == schedule_8.FORM_EXPORTS
    assert (found.min_instances, found.max_instances, found.exclusive_group) == (
        0,
        1,
        "ca/cpp_calculation",
    )


def test_the_form_holds_the_147_schedule_8_selections() -> None:
    found = form()

    assert len(found.capabilities) == 147
    assert set(found.capabilities) == FORM_STEPS


def test_the_return_keeps_only_the_copied_steps_of_the_form_and_totals_the_rest() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert schedule_8.STEPS <= selected
    shared = selected & FORM_STEPS
    assert {output for step in shared for output in step.produces.values()} == COPIED_PRODUCTS
    assert len(shared) == len(COPIED_PRODUCTS)


def test_each_part_is_not_over_30_kb_and_the_return_parts_hold_no_schedule_8_line() -> None:
    for name in (*FORM_PARTS, "05i_schedule_8_totals.yaml"):
        assert (PARTS / name).stat().st_size <= 30 * 1024, name
    for name in ("05_deductions.yaml", "08_non_refundable_credits.yaml"):
        text = (PARTS / name).read_text()
        for line in (
            "ca/cpp_first_additional_contributions",
            "ca/cpp_second_additional_contributions",
            "ca/cpp_enhanced_contributions\n",
            "ca/cpp_base_contributions\n",
        ):
            assert line not in text, (name, line)


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_an_input_of_the_manifest() -> None:
    assert schedule_8.INPUTS <= manifest().inputs.keys()


def test_the_instances_kind_is_a_record_list_with_no_fields() -> None:
    assert isinstance(SCHEDULE_8_INSTANCES, RecordListKind)
    assert SCHEDULE_8_INSTANCES.identifier == "ca/schedule_8_instances"
    assert SCHEDULE_8_INSTANCES.fields == ()


def test_the_catalog_registers_the_instances_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/schedule_8_instances") is SCHEDULE_8_INSTANCES


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_the_line_13_nothing_reads() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert schedule_8.OUTPUTS <= exports
    assert "ca/cpp_required_base_and_first_additional_contributions" not in exports
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_instances_and_derives_its_eight_kinds() -> None:
    found = composed()

    assert found.instances == SCHEDULE_8_INSTANCES
    assert {kind.identifier for kind in found.imports} == {
        "ca/t1139_return.t1139_business_income_on_return",
        "ca/t1139_return.t1139_professional_income_on_return",
        "ca/t1139_return.t1139_commission_income_on_return",
        "ca/t1139_return.t1139_farming_income_on_return",
        "ca/t1139_return.t1139_fishing_income_on_return",
    }
    assert [kind.identifier for kind in found.derived] == [
        f"ca/schedule_8.{export.removeprefix('ca/')}" for export in schedule_8.FORM_EXPORTS
    ]
    assert (found.min_instances, found.max_instances) == (0, 1)


def test_the_selections_inside_the_form_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == FORM_WIRING
